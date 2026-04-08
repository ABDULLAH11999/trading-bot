import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uvicorn
from pathlib import Path

import aiohttp
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app_storage import (
    get_user_admin_state,
    init_storage,
    list_payments,
    list_user_admin_states,
    payment_stats,
    record_payment,
    set_user_admin_state,
)
from bot_state import BotState, set_current_state
from performance_reports import build_pdf_bytes, build_report_filename
from pydantic import BaseModel
from config import settings
from smtp_mailer import MailDeliveryConfig, format_mail_delivery_error, send_access_code, send_registration_code
from stripe_billing import (
    SUBSCRIPTION_CURRENCY,
    SUBSCRIPTION_PRICE_CENTS,
    create_checkout_session,
    extract_payment_event,
    fetch_checkout_session,
    fetch_subscription,
    normalize_subscription,
    stripe_configured,
    stripe_publishable_key,
)
from user_profiles import (
    get_profile,
    hash_password,
    hash_verification_code,
    list_profiles,
    normalize_email,
    normalize_time_slots,
    save_profile,
    subscription_is_active,
    verify_password,
)

BASE_DIR = Path(__file__).resolve().parent
AUTH_COOKIE_NAME = "scalper_bot_auth"
ADMIN_COOKIE_NAME = "scalper_bot_admin"
logger = logging.getLogger(__name__)

app = FastAPI(
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
)
print("BACKEND VERSION: 1.0.32 - READY")
init_storage()
mode_switch_handler = None
bot_manager = None
_PUBLIC_IP_CACHE = {
    "value": "",
    "checked_at": 0,
    "source": "",
}

if settings.CORS_ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=True,
    )

if settings.APP_ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.APP_ALLOWED_HOSTS)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: https://s3.tradingview.com https://*.tradingview.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "script-src 'self' 'unsafe-inline' https://s3.tradingview.com https://*.tradingview.com; "
            "connect-src 'self' ws: wss: https: http:; "
            "frame-src 'self' https://s.tradingview.com https://*.tradingview.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if _request_is_secure(request):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(SecurityHeadersMiddleware)


def _auth_required():
    return True


async def _ensure_bot_manager_ready():
    global bot_manager
    if bot_manager is not None:
        return bot_manager
    from main import ScalperBot
    from bot_manager import MultiUserBotManager
    manager = MultiUserBotManager(ScalperBot)
    register_bot_manager(manager)
    return manager


async def _resume_enabled_user_bots():
    if not settings.AUTO_RESUME_USER_BOTS:
        logger.info("AUTO_RESUME_USER_BOTS is disabled; skipping startup bot resume.")
        return 0

    manager = await _ensure_bot_manager_ready()
    resumed = 0
    limit = int(settings.AUTO_RESUME_USER_BOT_LIMIT or 0)
    for profile in list_profiles():
        email = normalize_email(profile.get("email"))
        if not email:
            continue
        try:
            saved_state = BotState(user_email=email)
            should_resume = bool(saved_state.bot_enabled or saved_state.active_trades)
            if not should_resume:
                continue
            await manager.ensure_user_bot(email)
            resumed += 1
            if limit > 0 and resumed >= limit:
                logger.info("Startup bot resume limit reached (%s).", limit)
                break
        except Exception:
            # Continue booting even if one user's runtime cannot be restored.
            pass
    logger.info("Startup bot resume complete; resumed=%s limit=%s", resumed, limit)
    return resumed


@app.on_event("startup")
async def _startup_bot_manager():
    await _resume_enabled_user_bots()


def _auth_secret():
    base_secret = settings.AUTH_SESSION_SECRET or "email-allowlist-only"
    return hashlib.sha256(base_secret.encode("utf-8")).hexdigest()


def _admin_secret():
    base_secret = f"{settings.AUTH_SESSION_SECRET}:{settings.ADMIN_EMAIL}:{settings.ADMIN_PASS}"
    return hashlib.sha256(base_secret.encode("utf-8")).hexdigest()


def _request_is_secure(request: Request):
    if settings.FORCE_SECURE_COOKIES:
        return True
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto == "https":
        return True
    return str(request.url.scheme).lower() == "https"


def _build_auth_cookie_value(email):
    normalized = normalize_email(email)
    signature = hmac.new(
        _auth_secret().encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = json.dumps({"email": normalized, "sig": signature}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _build_admin_cookie_value(email):
    normalized = normalize_email(email)
    signature = hmac.new(
        _admin_secret().encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = json.dumps({"email": normalized, "sig": signature}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _parse_auth_cookie_value(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw_value.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception:
        return None

    email = normalize_email(payload.get("email"))
    signature = str(payload.get("sig") or "")
    if not email or not signature:
        return None

    expected = hmac.new(
        _auth_secret().encode("utf-8"),
        email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    profile = get_profile(email)
    access_state = get_user_admin_state(email)
    if not profile.get("password_hash"):
        return None
    if not access_state.get("is_active"):
        return None
    if not profile.get("email_verified") and not access_state.get("otp_bypass_allowed"):
        return None
    return email


def _parse_admin_cookie_value(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw_value.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception:
        return None
    email = normalize_email(payload.get("email"))
    signature = str(payload.get("sig") or "")
    if not email or not signature:
        return None
    expected = hmac.new(
        _admin_secret().encode("utf-8"),
        email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    if email != settings.ADMIN_EMAIL:
        return None
    return email


def _is_authenticated(request: Request):
    if not _auth_required():
        return True
    return bool(_parse_auth_cookie_value(request.cookies.get(AUTH_COOKIE_NAME, "")))


def _current_user_email(request: Request):
    if not _auth_required():
        return ""
    return _parse_auth_cookie_value(request.cookies.get(AUTH_COOKIE_NAME, "")) or ""


def _require_auth(request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required.")


def _is_admin_authenticated(request: Request):
    return bool(_parse_admin_cookie_value(request.cookies.get(ADMIN_COOKIE_NAME, "")))


def _require_admin(request: Request):
    if not _is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Admin authentication required.")


def _mask_saved_value(value):
    if not value:
        return ""
    return settings.mask_credential(value)


def _runtime_email(email):
    normalized = normalize_email(email)
    return normalized or "__default__@local"


async def _state_for_request(request: Request):
    email = _current_user_email(request)
    await _ensure_bot_manager_ready()
    if bot_manager is None:
        raise HTTPException(status_code=503, detail="Bot manager is not ready yet.")
    runtime_state = await bot_manager.get_state(email)
    set_current_state(runtime_state)
    return runtime_state, _runtime_email(email)


def _subscription_payload(profile):
    subscription = profile.get("subscription") or {}
    active = subscription_is_active(subscription)
    fee_cents = int(round(float(settings.REAL_MODE_FEE or 29) * 100))
    return {
        "configured": stripe_configured(),
        "active": active,
        "status": str(subscription.get("status") or "inactive").strip().lower(),
        "subscription_id": str(subscription.get("subscription_id") or "").strip(),
        "customer_id": str(subscription.get("customer_id") or "").strip(),
        "current_period_end": int(subscription.get("current_period_end") or 0),
        "current_period_start": int(subscription.get("current_period_start") or 0),
        "cancel_at_period_end": bool(subscription.get("cancel_at_period_end", False)),
        "price_cents": fee_cents,
        "currency": SUBSCRIPTION_CURRENCY,
    }


def _user_access_payload(email):
    return get_user_admin_state(email)


def _user_summary_payload(email):
    profile = get_profile(email)
    subscription = _subscription_payload(profile)
    preferred_mode = str(profile.get("preferred_mode") or "test").strip().lower()
    if preferred_mode not in {"test", "real"}:
        preferred_mode = "test"
    return {
        "email": normalize_email(email),
        "email_verified": bool(profile.get("email_verified")),
        "preferred_mode": preferred_mode,
        "subscription": subscription,
        "access": _user_access_payload(email),
    }


async def _sync_subscription_state(email, force=False):
    normalized = normalize_email(email)
    if not normalized:
        return _subscription_payload(get_profile(normalized))
    profile = get_profile(normalized)
    subscription = profile.get("subscription") or {}
    subscription_id = str(subscription.get("subscription_id") or "").strip()
    if not stripe_configured() or not subscription_id:
        return _subscription_payload(profile)
    now_ts = int(time.time())
    if not force and now_ts - int(subscription.get("last_synced_at") or 0) < 90:
        return _subscription_payload(profile)
    try:
        latest = await fetch_subscription(subscription_id)
        latest_invoice = (latest.get("latest_invoice") or {}) if isinstance(latest, dict) else {}
        payment_intent = latest_invoice.get("payment_intent") or {}
        if isinstance(payment_intent, dict) and payment_intent.get("id"):
            record_payment(
                email=normalized,
                amount_cents=int(payment_intent.get("amount") or 0),
                currency=str(payment_intent.get("currency") or SUBSCRIPTION_CURRENCY).strip().lower(),
                paid_at=int(payment_intent.get("created") or time.time()),
                payment_intent_id=str(payment_intent.get("id") or "").strip(),
                checkout_session_id=str((profile.get("subscription") or {}).get("checkout_session_id") or "").strip(),
                subscription_id=subscription_id,
                status=str(payment_intent.get("status") or "paid").strip().lower(),
            )
        normalized_subscription = normalize_subscription(latest)
        updated = save_profile(normalized, {"subscription": normalized_subscription})
        if subscription_is_active(normalized_subscription):
            set_user_admin_state(normalized, real_mode_enabled=True)
        return _subscription_payload(updated)
    except Exception:
        return _subscription_payload(profile)


def _current_origin(request: Request):
    if settings.PUBLIC_APP_URL:
        return settings.PUBLIC_APP_URL.rstrip("/")
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip()
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").strip()
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _require_real_subscription(email):
    access = _user_access_payload(email)
    if access.get("real_mode_enabled"):
        return
    summary = _subscription_payload(get_profile(email))
    if not summary.get("active"):
        raise HTTPException(status_code=402, detail=f"Real account mode requires an active ${float(settings.REAL_MODE_FEE or 29):.0f}/month subscription.")


def _require_saved_mode_keys(email, mode):
    profile = get_profile(email)
    credentials = ((profile.get("credentials") or {}).get(mode) or {})
    has_key = bool(str(credentials.get("api_key") or "").strip())
    has_secret = bool(str(credentials.get("api_secret") or "").strip())
    if has_key and has_secret:
        return
    mode_label = "real" if mode == "real" else "test"
    raise HTTPException(status_code=400, detail=f"Please save your {mode_label} Binance API key and secret before enabling the bot.")


def _api_config_payload(email):
    normalized = normalize_email(email)
    profile = get_profile(normalized)
    preferred_mode = str(profile.get("preferred_mode") or "test").strip().lower()
    credentials = profile.get("credentials") or {}
    subscription = _subscription_payload(profile)
    return {
        "email": normalized,
        "preferred_mode": preferred_mode if preferred_mode in {"test", "real"} else "test",
        "subscription": subscription,
        "access": _user_access_payload(email),
        "real_mode_fee": float(settings.REAL_MODE_FEE or 29),
        "selected_mode": preferred_mode if preferred_mode in {"test", "real"} else "test",
        "test": {
            "has_saved_key": bool(((credentials.get("test") or {}).get("api_key") or "").strip()),
            "has_saved_secret": bool(((credentials.get("test") or {}).get("api_secret") or "").strip()),
            "saved_key_masked": _mask_saved_value((credentials.get("test") or {}).get("api_key")),
            "saved_secret_masked": _mask_saved_value((credentials.get("test") or {}).get("api_secret")),
            "using_env_fallback": False,
            "env_available": settings.has_testnet_keys(),
        },
        "real": {
            "has_saved_key": bool(((credentials.get("real") or {}).get("api_key") or "").strip()),
            "has_saved_secret": bool(((credentials.get("real") or {}).get("api_secret") or "").strip()),
            "saved_key_masked": _mask_saved_value((credentials.get("real") or {}).get("api_key")),
            "saved_secret_masked": _mask_saved_value((credentials.get("real") or {}).get("api_secret")),
            "using_env_fallback": False,
            "env_available": False,
        },
    }


@app.get("/status")
async def get_status(request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    runtime_state, _ = await _state_for_request(request)
    payload = runtime_state.to_dict()
    payload["user"] = _user_summary_payload(email)
    payload["subscription"] = await _sync_subscription_state(email)
    return payload

@app.get("/health")
async def health():
    return {"status": "healthy"}


async def _fetch_public_server_ip():
    now_ts = int(time.time())
    if _PUBLIC_IP_CACHE["value"] and (now_ts - int(_PUBLIC_IP_CACHE["checked_at"] or 0) < 60):
        return {
            "public_ip": _PUBLIC_IP_CACHE["value"],
            "checked_at": _PUBLIC_IP_CACHE["checked_at"],
            "source": _PUBLIC_IP_CACHE["source"] or "cache",
        }

    providers = (
        ("https://api.ipify.org?format=json", "ipify"),
        ("https://ifconfig.me/all.json", "ifconfig.me"),
    )
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url, source in providers:
            try:
                async with session.get(url, ssl=False) as response:
                    if response.status != 200:
                        continue
                    payload = await response.json()
                    ip_value = str(payload.get("ip_addr") or payload.get("ip") or "").strip()
                    if not ip_value:
                        continue
                    _PUBLIC_IP_CACHE.update({
                        "value": ip_value,
                        "checked_at": now_ts,
                        "source": source,
                    })
                    return {
                        "public_ip": ip_value,
                        "checked_at": now_ts,
                        "source": source,
                    }
            except Exception:
                continue
    return {
        "public_ip": "",
        "checked_at": now_ts,
        "source": "",
    }


@app.get("/server/network-info")
async def server_network_info(request: Request):
    _require_auth(request)
    payload = await _fetch_public_server_ip()
    return {
        **payload,
        "note": "Use this current server IP when configuring Binance API IP restrictions. Render can change egress IP after redeploys or restarts.",
    }


def register_mode_switch_handler(handler):
    global mode_switch_handler
    mode_switch_handler = handler


def register_bot_manager(manager):
    global bot_manager
    bot_manager = manager

class SettingsUpdate(BaseModel):
    mode: str = None
    risk: float = None
    test_balance: float = None
    bot_enabled: bool = None
    account_mode: str = None


class PasswordLogin(BaseModel):
    email: str = ""
    password: str = ""


class RegisterRequest(BaseModel):
    email: str = ""
    password: str = ""


class VerifyCodeRequest(BaseModel):
    email: str = ""
    code: str = ""


class ResendCodeRequest(BaseModel):
    email: str = ""


class CheckoutSessionRequest(BaseModel):
    mode: str = "real"


class AdminLoginRequest(BaseModel):
    email: str = ""
    password: str = ""


class AdminUserUpdateRequest(BaseModel):
    is_active: bool | None = None
    real_mode_enabled: bool | None = None


class AdminTestEmailRequest(BaseModel):
    to_email: str = ""


class CredentialPair(BaseModel):
    api_key: str = ""
    api_secret: str = ""


class UserApiConfigUpdate(BaseModel):
    preferred_mode: str = "test"
    test: CredentialPair = CredentialPair()
    real: CredentialPair = CredentialPair()


class UserTradingPreferencesUpdate(BaseModel):
    favorite_pairs_enabled: bool = False
    favorite_pairs: list[str] = []


class TimeSlotRange(BaseModel):
    start: str = ""
    end: str = ""


class UserTimeSlotsUpdate(BaseModel):
    enabled: bool = False
    slots: list[TimeSlotRange] = []

class BulkCloseRequest(BaseModel):
    scope: str = "all"


@app.get("/auth/status")
async def auth_status(request: Request):
    email = _current_user_email(request)
    subscription = await _sync_subscription_state(email) if email else _subscription_payload(get_profile(""))
    return {
        "auth_required": _auth_required(),
        "authenticated": _is_authenticated(request),
        "email": email,
        "user": _user_summary_payload(email) if email else None,
        "smtp_configured": MailDeliveryConfig().is_configured(),
        "stripe_configured": stripe_configured(),
        "subscription": subscription,
        "real_mode_fee": float(settings.REAL_MODE_FEE or 29),
    }


@app.post("/auth/register")
async def auth_register(payload: RegisterRequest):
    email = normalize_email(payload.email)
    password = str(payload.password or "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if not MailDeliveryConfig().is_configured():
        raise HTTPException(status_code=500, detail="Mail delivery is not configured in .env.")

    existing = get_profile(email)
    if existing.get("email_verified") and existing.get("password_hash"):
        raise HTTPException(status_code=409, detail="This email is already registered. Please log in.")

    code = f"{secrets.randbelow(9000) + 1000:04d}"
    now_ts = int(time.time())
    try:
        await send_registration_code(email, code)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to send verification email: {format_mail_delivery_error(exc)}",
        ) from exc

    save_profile(email, {
        "password_hash": hash_password(password),
        "email_verified": False,
        "preferred_mode": "test",
        "verification": {
            "code_hash": hash_verification_code(email, code),
            "expires_at": now_ts + 300,
            "last_sent_at": now_ts,
            "attempts": 0,
            "purpose": "register",
        },
    })
    return {
        "status": "pending_verification",
        "email": email,
        "expires_in_seconds": 300,
        "message": "A 4-digit code was sent to your email.",
    }


@app.post("/auth/resend-code")
async def auth_resend_code(payload: ResendCodeRequest):
    email = normalize_email(payload.email)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    profile = get_profile(email)
    if not profile.get("password_hash"):
        raise HTTPException(status_code=404, detail="No pending registration found for this email.")
    if not MailDeliveryConfig().is_configured():
        raise HTTPException(status_code=500, detail="Mail delivery is not configured in .env.")

    now_ts = int(time.time())
    purpose = str((profile.get("verification") or {}).get("purpose") or "register").strip().lower() or "register"
    last_sent_at = int((profile.get("verification") or {}).get("last_sent_at") or 0)
    wait_seconds = 60 - (now_ts - last_sent_at)
    if wait_seconds > 0:
        raise HTTPException(status_code=429, detail=f"Please wait {wait_seconds} seconds before resending the code.")

    code = f"{secrets.randbelow(9000) + 1000:04d}"
    try:
        if purpose == "reactivate":
            await send_access_code(email, code, title="Reactivate your account", subtitle="Use this 4-digit code to reactivate your account and continue.")
        else:
            await send_registration_code(email, code)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to resend verification email: {format_mail_delivery_error(exc)}",
        ) from exc

    save_profile(email, {
        "verification": {
            "code_hash": hash_verification_code(email, code),
            "expires_at": now_ts + 300,
            "last_sent_at": now_ts,
            "attempts": 0,
            "purpose": purpose,
        },
    })
    return {
        "status": "resent",
        "email": email,
        "expires_in_seconds": 300,
    }


@app.post("/auth/verify-code")
async def auth_verify_code(request: Request, payload: VerifyCodeRequest):
    email = normalize_email(payload.email)
    code = str(payload.code or "").strip()
    if not email or not code:
        raise HTTPException(status_code=400, detail="Email and verification code are required.")
    profile = get_profile(email)
    verification = profile.get("verification") or {}
    if not profile.get("password_hash"):
        raise HTTPException(status_code=404, detail="No pending registration found for this email.")
    if int(verification.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(status_code=400, detail="Verification code expired. Please resend a new code.")
    if str(verification.get("code_hash") or "") != hash_verification_code(email, code):
        attempts = int(verification.get("attempts") or 0) + 1
        save_profile(email, {"verification": {"attempts": attempts}})
        raise HTTPException(status_code=401, detail="Invalid verification code.")

    purpose = str(verification.get("purpose") or "register").strip().lower() or "register"
    access_state = get_user_admin_state(email)

    save_profile(email, {
        "email_verified": True,
        "verification": {
            "code_hash": "",
            "expires_at": 0,
            "last_sent_at": int(time.time()),
            "attempts": 0,
            "purpose": "",
        },
    })
    if purpose == "reactivate":
        set_user_admin_state(email, is_active=True, requires_reverify=False, otp_bypass_allowed=False)
    if bot_manager is not None:
        await bot_manager.ensure_user_bot(email)

    response = JSONResponse({
        "status": "success",
        "authenticated": True,
        "email": email,
        "user": _user_summary_payload(email),
        "purpose": purpose,
    })
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=_build_auth_cookie_value(email),
        httponly=True,
        samesite="lax",
        secure=_request_is_secure(request),
    )
    return response


@app.post("/auth/login")
async def auth_login(request: Request, payload: PasswordLogin):
    email = normalize_email(payload.email)
    if not email:
        raise HTTPException(status_code=401, detail="Email is required.")
    profile = get_profile(email)
    access_state = get_user_admin_state(email)
    if not profile.get("password_hash"):
        raise HTTPException(status_code=401, detail="Account not found. Please register first.")
    if not access_state.get("is_active"):
        if access_state.get("requires_reverify"):
            if not MailDeliveryConfig().is_configured():
                raise HTTPException(status_code=500, detail="Mail delivery is not configured in .env.")
            code = f"{secrets.randbelow(9000) + 1000:04d}"
            now_ts = int(time.time())
            try:
                await send_access_code(email, code, title="Reactivate your account", subtitle="Use this 4-digit code to reactivate your account and continue.")
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to send reactivation code: {format_mail_delivery_error(exc)}",
                ) from exc
            save_profile(email, {
                "verification": {
                    "code_hash": hash_verification_code(email, code),
                    "expires_at": now_ts + 300,
                    "last_sent_at": now_ts,
                    "attempts": 0,
                    "purpose": "reactivate",
                },
            })
            raise HTTPException(status_code=403, detail="Your account was deactivated. A new 4-digit code has been emailed to reactivate it.")
        raise HTTPException(status_code=403, detail="Your account is inactive. Please contact admin.")
    if not profile.get("email_verified") and not access_state.get("otp_bypass_allowed"):
        raise HTTPException(status_code=401, detail="Please verify your email with the 4-digit code first.")
    if not verify_password(payload.password or "", profile.get("password_hash")):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    if bot_manager is not None:
        await bot_manager.ensure_user_bot(email)

    subscription = await _sync_subscription_state(email, force=True)
    response = JSONResponse({
        "status": "success",
        "authenticated": True,
        "email": email,
        "user": _user_summary_payload(email),
        "subscription": subscription,
    })
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=_build_auth_cookie_value(email),
        httponly=True,
        samesite="lax",
        secure=_request_is_secure(request),
    )
    return response


@app.post("/auth/logout")
async def auth_logout(request: Request):
    email = _current_user_email(request)
    if email:
        try:
            runtime_state, _ = await _state_for_request(request)
            runtime_state.bot_enabled = False
            runtime_state.bot_running = False
            runtime_state.save_state()
        except Exception:
            pass
    response = JSONResponse({"status": "success"})
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/user/api-config")
async def get_user_api_config(request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    await _sync_subscription_state(email)
    return _api_config_payload(email)


@app.post("/user/api-config")
async def update_user_api_config(request: Request, payload: UserApiConfigUpdate):
    _require_auth(request)
    email = _current_user_email(request)
    current_profile = get_profile(email)
    current_credentials = current_profile.get("credentials") or {}
    preferred_mode = str(payload.preferred_mode or "test").strip().lower()
    if preferred_mode not in {"test", "real"}:
        preferred_mode = "test"

    updated_profile = save_profile(email, {
        "preferred_mode": preferred_mode,
        "credentials": {
            "test": {
                "api_key": payload.test.api_key or ((current_credentials.get("test") or {}).get("api_key") or ""),
                "api_secret": payload.test.api_secret or ((current_credentials.get("test") or {}).get("api_secret") or ""),
            },
            "real": {
                "api_key": payload.real.api_key or ((current_credentials.get("real") or {}).get("api_key") or ""),
                "api_secret": payload.real.api_secret or ((current_credentials.get("real") or {}).get("api_secret") or ""),
            },
        },
    })
    return {
        "status": "success",
        "config": _api_config_payload(updated_profile.get("email") or email),
    }


@app.get("/billing/status")
async def billing_status(request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    subscription = await _sync_subscription_state(email, force=True)
    return {
        "email": email,
        "subscription": subscription,
        "stripe_publishable_key": stripe_publishable_key(),
        "stripe_configured": stripe_configured(),
        "real_mode_fee": float(settings.REAL_MODE_FEE or 29),
    }


@app.post("/billing/create-checkout-session")
async def billing_create_checkout_session(request: Request, payload: CheckoutSessionRequest):
    _require_auth(request)
    email = _current_user_email(request)
    mode = str(payload.mode or "real").strip().lower()
    if mode != "real":
        raise HTTPException(status_code=400, detail="Checkout is only required for real mode.")
    if not stripe_configured():
        raise HTTPException(status_code=500, detail="Stripe is not configured in .env.")

    profile = get_profile(email)
    if subscription_is_active((profile.get("subscription") or {})):
        return {
            "status": "already_active",
            "subscription": _subscription_payload(profile),
        }

    origin = _current_origin(request)
    session = await create_checkout_session(
        email=email,
        success_url=f"{origin}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/?billing=cancelled",
        customer_id=str((profile.get("subscription") or {}).get("customer_id") or "").strip(),
    )
    customer_id = str(session.get("customer") or "").strip()
    save_profile(email, {
        "subscription": {
            "customer_id": customer_id,
            "checkout_session_id": str(session.get("id") or "").strip(),
            "last_synced_at": int(time.time()),
        },
    })
    return {
        "status": "created",
        "checkout_url": session.get("url"),
        "session_id": session.get("id"),
        "real_mode_fee": float(settings.REAL_MODE_FEE or 29),
    }


@app.get("/billing/success")
async def billing_success(session_id: str = Query(default="")):
    session_id = str(session_id or "").strip()
    if not session_id:
        return HTMLResponse("<script>window.location.replace('/?billing=missing');</script>")
    try:
        session = await fetch_checkout_session(session_id)
        email = normalize_email(((session.get("metadata") or {}).get("email")) or (session.get("customer_details") or {}).get("email") or "")
        subscription_obj = session.get("subscription") or {}
        if not isinstance(subscription_obj, dict):
            subscription_obj = await fetch_subscription(str(subscription_obj).strip())
        customer_obj = session.get("customer") or {}
        if not isinstance(customer_obj, dict):
            customer_obj = {"id": str(customer_obj or "").strip()}
        if email:
            normalized_subscription = normalize_subscription(subscription_obj)
            normalized_subscription["customer_id"] = str(customer_obj.get("id") or session.get("customer") or "").strip()
            normalized_subscription["checkout_session_id"] = session_id
            save_profile(email, {"subscription": normalized_subscription})
            if subscription_is_active(normalized_subscription):
                set_user_admin_state(email, real_mode_enabled=True)
            payment_event = extract_payment_event(session)
            if payment_event.get("payment_intent_id"):
                record_payment(
                    email=email,
                    amount_cents=payment_event["amount_cents"],
                    currency=payment_event["currency"],
                    paid_at=payment_event["paid_at"],
                    payment_intent_id=payment_event["payment_intent_id"],
                    checkout_session_id=payment_event["checkout_session_id"],
                    subscription_id=payment_event["subscription_id"],
                    status="paid",
                )
    except Exception:
        pass
    return HTMLResponse("<script>window.location.replace('/?billing=success');</script>")


@app.get("/admin")
async def admin_index():
    admin_file = BASE_DIR / "frontend" / "admin.html"
    if not admin_file.exists():
        raise HTTPException(status_code=404, detail="Admin frontend not found.")
    return HTMLResponse(admin_file.read_text(encoding="utf-8"))


@app.get("/admin/auth/status")
async def admin_auth_status(request: Request):
    return {
        "authenticated": _is_admin_authenticated(request),
        "email": settings.ADMIN_EMAIL if _is_admin_authenticated(request) else "",
    }


@app.post("/admin/auth/login")
async def admin_auth_login(request: Request, payload: AdminLoginRequest):
    email = normalize_email(payload.email)
    password = str(payload.password or "")
    if email != settings.ADMIN_EMAIL or not hmac.compare_digest(password, settings.ADMIN_PASS):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    response = JSONResponse({"status": "success", "email": email})
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=_build_admin_cookie_value(email),
        httponly=True,
        samesite="lax",
        secure=_request_is_secure(request),
    )
    return response


@app.post("/admin/auth/logout")
async def admin_auth_logout():
    response = JSONResponse({"status": "success"})
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


@app.post("/admin/test-email")
async def admin_test_email(request: Request, payload: AdminTestEmailRequest):
    _require_admin(request)
    to_email = normalize_email(payload.to_email)
    if not to_email:
        raise HTTPException(status_code=400, detail="Email is required.")
    try:
        await send_access_code(
            to_email,
            "1234",
            title="Test Email",
            subtitle="This is a test message from the Scalper Bot service.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to send test email: {format_mail_delivery_error(exc)}",
        ) from exc
    return {"status": "sent", "email": to_email}


def _admin_users_payload():
    payments = list_payments()
    paid_lookup = {payment["email"] for payment in payments}
    admin_rows = {row["email"]: row for row in list_user_admin_states()}
    users = []
    for profile in list_profiles():
        email = normalize_email(profile.get("email"))
        if not email:
            continue
        access = admin_rows.get(email) or get_user_admin_state(email)
        subscription = _subscription_payload(profile)
        effective_real_mode_enabled = bool(access.get("real_mode_enabled")) or bool(subscription.get("active"))
        users.append({
            "email": email,
            "email_verified": bool(profile.get("email_verified")),
            "is_active": bool(access.get("is_active")),
            "requires_reverify": bool(access.get("requires_reverify")),
            "otp_bypass_allowed": bool(access.get("otp_bypass_allowed")),
            "real_mode_enabled": effective_real_mode_enabled,
            "paid": email in paid_lookup or bool(subscription.get("active")),
            "subscription_active": bool(subscription.get("active")),
            "subscription_end": int(subscription.get("current_period_end") or 0),
            "preferred_mode": str(profile.get("preferred_mode") or "test"),
        })
    users.sort(key=lambda item: item["email"])
    return users


@app.get("/admin/overview")
async def admin_overview(request: Request):
    _require_admin(request)
    users = _admin_users_payload()
    pay_stats = payment_stats()
    return {
        "stats": {
            "total_users": len(users),
            "paid_users": pay_stats["paid_user_count"],
            "total_payments": pay_stats["total_payments"],
            "total_amount_cents": pay_stats["total_amount_cents"],
        },
        "real_mode_fee": float(settings.REAL_MODE_FEE or 29),
    }


@app.get("/admin/users")
async def admin_users(request: Request):
    _require_admin(request)
    return {
        "users": _admin_users_payload(),
    }


@app.post("/admin/users/{email:path}")
async def admin_update_user(email: str, payload: AdminUserUpdateRequest, request: Request):
    _require_admin(request)
    normalized = normalize_email(email)
    profile = get_profile(normalized)
    if not profile.get("password_hash"):
        raise HTTPException(status_code=404, detail="User not found.")
    current = get_user_admin_state(normalized)
    updates = {}
    if payload.is_active is not None:
        if payload.is_active:
            updates["is_active"] = True
            updates["requires_reverify"] = False
            updates["otp_bypass_allowed"] = not bool(profile.get("email_verified"))
        else:
            updates["is_active"] = False
            updates["requires_reverify"] = True
            updates["otp_bypass_allowed"] = False
            save_profile(normalized, {
                "email_verified": False,
                "verification": {
                    "code_hash": "",
                    "expires_at": 0,
                    "last_sent_at": 0,
                    "attempts": 0,
                    "purpose": "reactivate",
                },
            })
    if payload.real_mode_enabled is not None:
        updates["real_mode_enabled"] = bool(payload.real_mode_enabled)
    if not updates:
        raise HTTPException(status_code=400, detail="No admin updates were provided.")
    state = set_user_admin_state(normalized, **updates)
    return {
        "status": "success",
        "user": {
            "email": normalized,
            **state,
        },
    }


@app.get("/admin/payments")
async def admin_payments(request: Request):
    _require_admin(request)
    return {
        "payments": list_payments(),
        "real_mode_fee": float(settings.REAL_MODE_FEE or 29),
    }


def _normalize_pair_symbol(symbol):
    normalized = str(symbol or "").strip().upper().replace("-", "/").replace(" ", "")
    if not normalized:
        return ""
    if "/" not in normalized and normalized.endswith(settings.QUOTE_ASSET):
        base_asset = normalized[: -len(settings.QUOTE_ASSET)]
        if base_asset:
            normalized = f"{base_asset}/{settings.QUOTE_ASSET}"
    return normalized


def _trading_preferences_payload(email):
    profile = get_profile(email)
    favorite_pairs = []
    seen_pairs = set()
    for symbol in (profile.get("favorite_pairs") or []):
        normalized_symbol = _normalize_pair_symbol(symbol)
        if not normalized_symbol or normalized_symbol in seen_pairs:
            continue
        seen_pairs.add(normalized_symbol)
        favorite_pairs.append(normalized_symbol)
    return {
        "email": normalize_email(email),
        "favorite_pairs_enabled": bool(profile.get("favorite_pairs_enabled", False)),
        "favorite_pairs": favorite_pairs,
    }


def _time_slots_payload(email):
    profile = get_profile(email)
    return {
        "email": normalize_email(email),
        "enabled": bool(profile.get("time_slots_enabled", False)),
        "slots": normalize_time_slots(profile.get("time_slots") or []),
    }


@app.get("/user/trading-preferences")
async def get_user_trading_preferences(request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    return _trading_preferences_payload(email)


@app.post("/user/trading-preferences")
async def update_user_trading_preferences(request: Request, payload: UserTradingPreferencesUpdate):
    _require_auth(request)
    email = _current_user_email(request)
    updated_profile = save_profile(email, {
        "favorite_pairs_enabled": payload.favorite_pairs_enabled,
        "favorite_pairs": [_normalize_pair_symbol(symbol) for symbol in (payload.favorite_pairs or [])],
    })
    preferences = _trading_preferences_payload(updated_profile.get("email") or email)
    if bot_manager is not None:
        await bot_manager.update_user_preferences(email, preferences)
    return {
        "status": "success",
        "preferences": preferences,
    }


@app.get("/user/time-slots")
async def get_user_time_slots(request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    return _time_slots_payload(email)


@app.post("/user/time-slots")
async def update_user_time_slots(request: Request, payload: UserTimeSlotsUpdate):
    _require_auth(request)
    email = _current_user_email(request)
    try:
        updated_profile = save_profile(email, {
            "time_slots_enabled": payload.enabled,
            "time_slots": [{"start": slot.start, "end": slot.end} for slot in (payload.slots or [])],
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    slots_payload = _time_slots_payload(updated_profile.get("email") or email)
    if bot_manager is not None:
        favorite_payload = _trading_preferences_payload(updated_profile.get("email") or email)
        combined_preferences = {
            "favorite_pairs_enabled": favorite_payload.get("favorite_pairs_enabled", False),
            "favorite_pairs": favorite_payload.get("favorite_pairs") or [],
            "time_slots_enabled": slots_payload.get("enabled", False),
            "time_slots": slots_payload.get("slots") or [],
        }
        await bot_manager.update_user_preferences(email, combined_preferences)
    return {
        "status": "success",
        "time_slots": slots_payload,
    }


@app.get("/market/pair-options")
async def get_market_pair_options(request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    if bot_manager is None:
        raise HTTPException(status_code=503, detail="Bot manager is not ready yet.")
    return {
        "options": await bot_manager.get_pair_options(email),
    }

@app.post("/update_settings")
async def update_settings(request: Request, update: SettingsUpdate):
    _require_auth(request)
    runtime_state, current_email = await _state_for_request(request)
    account_mode = str(update.account_mode or runtime_state.account_mode or "test").strip().lower()
    if update.mode:
        runtime_state.bot_mode = update.mode
        runtime_state.add_log(f"Bot mode changed to: {update.mode}")
    if update.risk is not None:
        runtime_state.risk_percentage = max(0.0, min(100.0, update.risk))
        runtime_state.add_log(f"Risk percentage updated to: {runtime_state.risk_percentage}%")
    if update.test_balance is not None:
        runtime_state.set_test_balance_baseline(update.test_balance)
        runtime_state.add_log(f"Simulated balance set to: {update.test_balance}")
    if update.bot_enabled is not None:
        was_enabled = bool(runtime_state.bot_enabled)
        target_mode = str(account_mode or runtime_state.account_mode or "test").strip().lower()
        if update.bot_enabled and not was_enabled:
            if target_mode == "real":
                await _sync_subscription_state(current_email, force=True)
                _require_real_subscription(current_email)
            _require_saved_mode_keys(current_email, target_mode)
        runtime_state.bot_enabled = update.bot_enabled
        if runtime_state.bot_enabled and not was_enabled:
            runtime_state.start_time = time.time()
            runtime_state.bot_running = True
        elif not runtime_state.bot_enabled:
            runtime_state.bot_running = False
        status_text = "ENABLED" if runtime_state.bot_enabled else "DISABLED"
        runtime_state.add_log(f"Bot Trading {status_text}")
    if update.account_mode:
        if update.account_mode == "real":
            await _sync_subscription_state(current_email, force=True)
            _require_real_subscription(current_email)
        if bot_manager is None and mode_switch_handler is None:
            raise HTTPException(status_code=503, detail="Account mode switching is not ready yet.")
        try:
            if bot_manager is not None:
                result = await bot_manager.switch_account_mode(current_email, update.account_mode)
            else:
                result = await mode_switch_handler(update.account_mode, current_email)
            runtime_state.save_state()
            return {"status": "success", **result}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    runtime_state.save_state()
    return {"status": "success"}

@app.post("/reset_bot")
async def reset_bot(request: Request):
    _require_auth(request)
    """Reset PnL and trade history."""
    runtime_state, _ = await _state_for_request(request)
    runtime_state.reset_state()
    return {"status": "success"}

@app.post("/test_trade")
async def test_trade(request: Request):
    _require_auth(request)
    """Trigger the best currently available manual setup immediately."""
    runtime_state, _ = await _state_for_request(request)
    runtime_state.add_log("Bot Enforce to take best trade")
    email = _current_user_email(request)
    if bot_manager is None:
        runtime_state.manual_trade_trigger = True
        return {"status": "queued"}
    result = await bot_manager.execute_manual_best_setup(email)
    status = str((result or {}).get("status") or "").strip().lower()
    detail = str((result or {}).get("detail") or "").strip()
    symbol = str((result or {}).get("symbol") or "").strip()
    if status == "triggered" and symbol:
        runtime_state.add_log(f"Bot Enforce result: best trade triggered for {symbol}.")
    elif status == "skipped":
        runtime_state.add_log(f"Bot Enforce result: skipped ({detail or 'no detail'}).")
    return result

@app.post("/close_trade/{symbol:path}")
async def close_trade(symbol: str, request: Request):
    _require_auth(request)
    """Signal the bot to manually close an active trade."""
    runtime_state, _ = await _state_for_request(request)
    if symbol in runtime_state.active_trades:
        runtime_state.manual_close_flags[symbol] = True
        runtime_state.add_log(f"Manual close requested for {symbol}.")
        return {"status": "triggered"}
    runtime_state.add_log(f"Manual close requested for {symbol}, but no active trade was found.")
    runtime_state.save_state()
    return {"status": "not_found", "error": f"No active trade for {symbol}"}


@app.post("/close_trades")
async def close_trades(payload: BulkCloseRequest, request: Request):
    _require_auth(request)
    runtime_state, _ = await _state_for_request(request)
    scope = str(payload.scope or "all").strip().lower()
    if scope not in {"all", "profit", "loss"}:
        raise HTTPException(status_code=400, detail="Invalid close scope. Use all, profit, or loss.")

    targets = []
    for symbol, trade in (runtime_state.active_trades or {}).items():
        trade_pnl = float(getattr(trade, "pnl", 0.0) or 0.0)
        if scope == "all":
            targets.append(symbol)
        elif scope == "profit" and trade_pnl > 0.0:
            targets.append(symbol)
        elif scope == "loss" and trade_pnl < 0.0:
            targets.append(symbol)

    if not targets:
        label = {
            "all": "ALL active trades",
            "profit": "PROFIT active trades",
            "loss": "LOSS active trades",
        }[scope]
        runtime_state.add_log(f"Manual bulk close requested for {label}, but no matching active trades were found.")
        runtime_state.save_state()
        return {"status": "no_match", "count": 0, "scope": scope, "symbols": []}

    for symbol in targets:
        runtime_state.manual_close_flags[symbol] = True

    label = {
        "all": "ALL active trades",
        "profit": "PROFIT active trades",
        "loss": "LOSS active trades",
    }[scope]
    runtime_state.add_log(f"Manual bulk close requested for {label} ({len(targets)}).")
    return {"status": "triggered", "count": len(targets), "scope": scope, "symbols": targets}


@app.get("/reports/summary")
async def performance_report(request: Request, range: str = Query(default="overall")):
    _require_auth(request)
    runtime_state, _ = await _state_for_request(request)
    return runtime_state.get_report_payload(range)


@app.get("/reports/download")
async def download_performance_report(request: Request, range: str = Query(default="overall")):
    _require_auth(request)
    runtime_state, _ = await _state_for_request(request)
    report = runtime_state.get_report_payload(range)
    pdf_bytes = build_pdf_bytes(report)
    filename = build_report_filename(report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/chart/{symbol:path}")
async def chart_payload(symbol: str, request: Request):
    _require_auth(request)
    email = _current_user_email(request)
    if bot_manager is None:
        raise HTTPException(status_code=503, detail="Bot manager is not ready yet.")
    payload = await bot_manager.get_chart_payload(email, symbol)
    if not payload:
        raise HTTPException(status_code=404, detail="Chart data unavailable for this symbol.")
    return payload


def _restart_response():
    return HTMLResponse(
        content="""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Restarting App</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; background:#0f1220; color:#e5e7eb; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
    .box { padding:22px 26px; border:1px solid rgba(255,255,255,0.15); border-radius:12px; background:rgba(255,255,255,0.04); }
  </style>
</head>
<body>
  <div class="box">Restart requested. Returning to dashboard...</div>
  <script>setTimeout(() => { window.location.replace('/'); }, 900);</script>
</body>
</html>
        """.strip()
    )


@app.get("/restart")
async def restart_app(request: Request):
    _require_auth(request)
    return _restart_response()


@app.post("/restart")
async def restart_app_post(request: Request):
    _require_auth(request)
    return _restart_response()

app.mount("/", StaticFiles(directory=str(BASE_DIR / "frontend"), html=True), name="frontend")

def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="error")
    server = uvicorn.Server(config)
    return server.serve()

if __name__ == "__main__":
    asyncio.run(run_api())
