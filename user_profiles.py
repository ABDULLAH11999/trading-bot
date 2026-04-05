import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = Path(__file__).resolve().parent
USER_PROFILES_FILE = BASE_DIR / "data" / "user_profiles.json"
_LOCK = threading.RLock()
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_MINUTES_PER_DAY = 24 * 60
_PASSWORD_ITERATIONS = 390000


def _build_fernet():
    secret = (
        os.getenv("APP_ENCRYPTION_KEY")
        or os.getenv("APP_ENCRYPTION_SECRET")
        or os.getenv("CREDENTIAL_ENCRYPTION_KEY")
        or os.getenv("SECRET_KEY")
        or os.getenv("APP_PASSWORD")
        or "scalper-bot-local-fallback-key"
    ).strip()
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


_FERNET = _build_fernet()


def normalize_email(email):
    return str(email or "").strip().lower()


def email_storage_key(email):
    normalized = normalize_email(email)
    if not normalized:
        return "default"
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "default"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{slug}_{digest}"


def user_data_dir(email):
    return BASE_DIR / "data" / "users" / email_storage_key(email)


def _default_profile(email):
    normalized = normalize_email(email)
    return {
        "email": normalized,
        "password_hash": "",
        "email_verified": False,
        "verification": {
            "code_hash": "",
            "expires_at": 0,
            "last_sent_at": 0,
            "attempts": 0,
            "purpose": "",
        },
        "subscription": {
            "customer_id": "",
            "subscription_id": "",
            "checkout_session_id": "",
            "status": "inactive",
            "current_period_end": 0,
            "current_period_start": 0,
            "cancel_at_period_end": False,
            "last_synced_at": 0,
        },
        "preferred_mode": "test",
        "favorite_pairs_enabled": False,
        "favorite_pairs": [],
        "time_slots_enabled": False,
        "time_slots": [],
        "credentials": {
            "test": {
                "api_key": "",
                "api_secret": "",
            },
            "real": {
                "api_key": "",
                "api_secret": "",
            },
        },
    }


def _time_to_minutes(value):
    text = str(value or "").strip()
    match = _TIME_PATTERN.match(text)
    if not match:
        raise ValueError("Time slots must use HH:MM 24-hour format.")
    return int(match.group(1)) * 60 + int(match.group(2))


def _minutes_to_time(minutes):
    hour = int(minutes // 60) % 24
    minute = int(minutes % 60)
    return f"{hour:02d}:{minute:02d}"


def _slot_segments(start_minutes, end_minutes):
    if start_minutes == end_minutes:
        raise ValueError("Time slot start and end cannot be the same.")
    if start_minutes < end_minutes:
        return [(start_minutes, end_minutes)]
    return [(start_minutes, _MINUTES_PER_DAY), (0, end_minutes)]


def normalize_time_slots(raw_slots):
    normalized_slots = []
    seen = set()
    segments = []

    for raw_slot in (raw_slots or []):
        if not isinstance(raw_slot, dict):
            continue
        start_text = str(raw_slot.get("start") or raw_slot.get("start_time") or "").strip()
        end_text = str(raw_slot.get("end") or raw_slot.get("end_time") or "").strip()
        if not start_text or not end_text:
            continue

        start_minutes = _time_to_minutes(start_text)
        end_minutes = _time_to_minutes(end_text)
        key = (start_minutes, end_minutes)
        if key in seen:
            continue
        seen.add(key)

        slot_segments = _slot_segments(start_minutes, end_minutes)
        segments.extend(slot_segments)
        normalized_slots.append({
            "start_minutes": start_minutes,
            "end_minutes": end_minutes,
            "start": _minutes_to_time(start_minutes),
            "end": _minutes_to_time(end_minutes),
        })

    segments.sort(key=lambda item: (item[0], item[1]))
    previous_end = -1
    for start, end in segments:
        if start < previous_end:
            raise ValueError("Time slots cannot overlap.")
        previous_end = max(previous_end, end)

    normalized_slots.sort(key=lambda slot: (slot["start_minutes"], slot["end_minutes"]))
    return [{"start": slot["start"], "end": slot["end"]} for slot in normalized_slots]


def _load_all():
    if not USER_PROFILES_FILE.exists():
        return {}
    try:
        with USER_PROFILES_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _save_all(payload):
    USER_PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USER_PROFILES_FILE.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _encrypt_secret(value):
    plain = str(value or "").strip()
    if not plain:
        return ""
    return _FERNET.encrypt(plain.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value):
    token = str(value or "").strip()
    if not token:
        return ""
    try:
        return _FERNET.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return token


def hash_password(password):
    raw_password = str(password or "")
    if not raw_password:
        raise ValueError("Password is required.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt, _PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PASSWORD_ITERATIONS,
        base64.b64encode(salt).decode("utf-8"),
        base64.b64encode(digest).decode("utf-8"),
    )


def verify_password(password, encoded_value):
    encoded = str(encoded_value or "").strip()
    raw_password = str(password or "")
    if not encoded or not raw_password:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        expected_digest = base64.b64decode(digest_b64.encode("utf-8"))
        candidate = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(candidate, expected_digest)
    except Exception:
        return False


def hash_verification_code(email, code):
    normalized = normalize_email(email)
    payload = f"{normalized}:{str(code or '').strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def subscription_is_active(subscription):
    data = subscription or {}
    status = str(data.get("status") or "").strip().lower()
    end_ts = int(data.get("current_period_end") or 0)
    now_ts = int(time.time())
    if status not in {"active", "trialing"}:
        return False
    return end_ts == 0 or end_ts > now_ts


def get_profile(email):
    normalized = normalize_email(email)
    if not normalized:
        return _default_profile("")

    with _LOCK:
        all_profiles = _load_all()
        profile = all_profiles.get(normalized)
        if not isinstance(profile, dict):
            return _default_profile(normalized)

        merged = _default_profile(normalized)
        merged["password_hash"] = str(profile.get("password_hash") or "").strip()
        merged["email_verified"] = bool(profile.get("email_verified", False))
        stored_verification = profile.get("verification") or {}
        merged["verification"]["code_hash"] = str(stored_verification.get("code_hash") or "").strip()
        merged["verification"]["expires_at"] = int(stored_verification.get("expires_at") or 0)
        merged["verification"]["last_sent_at"] = int(stored_verification.get("last_sent_at") or 0)
        merged["verification"]["attempts"] = int(stored_verification.get("attempts") or 0)
        merged["verification"]["purpose"] = str(stored_verification.get("purpose") or "").strip()
        stored_subscription = profile.get("subscription") or {}
        merged["subscription"]["customer_id"] = str(stored_subscription.get("customer_id") or "").strip()
        merged["subscription"]["subscription_id"] = str(stored_subscription.get("subscription_id") or "").strip()
        merged["subscription"]["checkout_session_id"] = str(stored_subscription.get("checkout_session_id") or "").strip()
        merged["subscription"]["status"] = str(stored_subscription.get("status") or "inactive").strip().lower()
        merged["subscription"]["current_period_end"] = int(stored_subscription.get("current_period_end") or 0)
        merged["subscription"]["current_period_start"] = int(stored_subscription.get("current_period_start") or 0)
        merged["subscription"]["cancel_at_period_end"] = bool(stored_subscription.get("cancel_at_period_end", False))
        merged["subscription"]["last_synced_at"] = int(stored_subscription.get("last_synced_at") or 0)
        merged["preferred_mode"] = str(profile.get("preferred_mode") or "test").strip().lower()
        merged["favorite_pairs_enabled"] = bool(profile.get("favorite_pairs_enabled", False))
        merged["favorite_pairs"] = [
            str(symbol or "").strip().upper()
            for symbol in (profile.get("favorite_pairs") or [])
            if str(symbol or "").strip()
        ]
        merged["time_slots_enabled"] = bool(profile.get("time_slots_enabled", False))
        try:
            merged["time_slots"] = normalize_time_slots(profile.get("time_slots") or [])
        except ValueError:
            merged["time_slots"] = []
        stored_credentials = profile.get("credentials") or {}
        for mode in ("test", "real"):
            mode_credentials = stored_credentials.get(mode) or {}
            merged["credentials"][mode]["api_key"] = _decrypt_secret(mode_credentials.get("api_key"))
            merged["credentials"][mode]["api_secret"] = _decrypt_secret(mode_credentials.get("api_secret"))
        return merged


def save_profile(email, updates):
    normalized = normalize_email(email)
    if not normalized:
        raise ValueError("A valid email is required.")

    with _LOCK:
        all_profiles = _load_all()
        current = get_profile(normalized)
        if "password_hash" in updates:
            current["password_hash"] = str(updates.get("password_hash") or "").strip()
        if "email_verified" in updates:
            current["email_verified"] = bool(updates.get("email_verified"))
        if "verification" in updates:
            verification_update = updates.get("verification") or {}
            for field in ("code_hash", "expires_at", "last_sent_at", "attempts", "purpose"):
                if field in verification_update:
                    if field == "code_hash":
                        current["verification"][field] = str(verification_update.get(field) or "").strip()
                    elif field == "purpose":
                        current["verification"][field] = str(verification_update.get(field) or "").strip()
                    else:
                        current["verification"][field] = int(verification_update.get(field) or 0)
            current["verification"]["expires_at"] = int(current["verification"].get("expires_at") or 0)
            current["verification"]["last_sent_at"] = int(current["verification"].get("last_sent_at") or 0)
            current["verification"]["attempts"] = int(current["verification"].get("attempts") or 0)
        if "subscription" in updates:
            subscription_update = updates.get("subscription") or {}
            for field in ("customer_id", "subscription_id", "checkout_session_id", "status"):
                if field in subscription_update:
                    current["subscription"][field] = str(subscription_update.get(field) or "").strip()
            for field in ("current_period_end", "current_period_start", "last_synced_at"):
                if field in subscription_update:
                    current["subscription"][field] = int(subscription_update.get(field) or 0)
            if "cancel_at_period_end" in subscription_update:
                current["subscription"]["cancel_at_period_end"] = bool(subscription_update.get("cancel_at_period_end"))
        current["preferred_mode"] = str(updates.get("preferred_mode") or current.get("preferred_mode") or "test").strip().lower()
        if current["preferred_mode"] not in {"test", "real"}:
            current["preferred_mode"] = "test"
        if "favorite_pairs_enabled" in updates:
            current["favorite_pairs_enabled"] = bool(updates.get("favorite_pairs_enabled"))
        if "favorite_pairs" in updates:
            deduped_pairs = []
            seen_pairs = set()
            for symbol in (updates.get("favorite_pairs") or []):
                normalized_symbol = str(symbol or "").strip().upper()
                if not normalized_symbol or normalized_symbol in seen_pairs:
                    continue
                seen_pairs.add(normalized_symbol)
                deduped_pairs.append(normalized_symbol)
            current["favorite_pairs"] = deduped_pairs
        if "time_slots_enabled" in updates:
            current["time_slots_enabled"] = bool(updates.get("time_slots_enabled"))
        if "time_slots" in updates:
            current["time_slots"] = normalize_time_slots(updates.get("time_slots") or [])

        updated_credentials = updates.get("credentials") or {}
        for mode in ("test", "real"):
            mode_credentials = updated_credentials.get(mode)
            if not isinstance(mode_credentials, dict):
                continue
            current["credentials"][mode]["api_key"] = str(mode_credentials.get("api_key") or "").strip()
            current["credentials"][mode]["api_secret"] = str(mode_credentials.get("api_secret") or "").strip()

        profile_to_store = json.loads(json.dumps(current))
        for mode in ("test", "real"):
            profile_to_store["credentials"][mode]["api_key"] = _encrypt_secret(current["credentials"][mode]["api_key"])
            profile_to_store["credentials"][mode]["api_secret"] = _encrypt_secret(current["credentials"][mode]["api_secret"])

        all_profiles[normalized] = profile_to_store
        _save_all(all_profiles)
        return current


def list_profiles():
    with _LOCK:
        all_profiles = _load_all()
        return [get_profile(email) for email in sorted(all_profiles.keys())]
