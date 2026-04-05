import sqlite3
import threading
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "app.db"
_LOCK = threading.RLock()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_storage():
    with _LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_admin_state (
                    email TEXT PRIMARY KEY,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    requires_reverify INTEGER NOT NULL DEFAULT 0,
                    otp_bypass_allowed INTEGER NOT NULL DEFAULT 0,
                    real_mode_enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'usd',
                    paid_at INTEGER NOT NULL DEFAULT 0,
                    payment_intent_id TEXT NOT NULL DEFAULT '',
                    checkout_session_id TEXT NOT NULL DEFAULT '',
                    subscription_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'paid'
                )
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_intent_unique ON payment_events(payment_intent_id)"
            )
            connection.commit()
        finally:
            connection.close()


def get_user_admin_state(email):
    normalized = str(email or "").strip().lower()
    if not normalized:
        return {
            "email": "",
            "is_active": True,
            "requires_reverify": False,
            "otp_bypass_allowed": False,
            "real_mode_enabled": False,
            "updated_at": 0,
        }
    init_storage()
    with _LOCK:
        connection = _connect()
        try:
            row = connection.execute(
                "SELECT email, is_active, requires_reverify, otp_bypass_allowed, real_mode_enabled, updated_at FROM user_admin_state WHERE email = ?",
                (normalized,),
            ).fetchone()
        finally:
            connection.close()
    if not row:
        return {
            "email": normalized,
            "is_active": True,
            "requires_reverify": False,
            "otp_bypass_allowed": False,
            "real_mode_enabled": False,
            "updated_at": 0,
        }
    return {
        "email": normalized,
        "is_active": bool(row["is_active"]),
        "requires_reverify": bool(row["requires_reverify"]),
        "otp_bypass_allowed": bool(row["otp_bypass_allowed"]),
        "real_mode_enabled": bool(row["real_mode_enabled"]),
        "updated_at": int(row["updated_at"] or 0),
    }


def set_user_admin_state(email, **updates):
    normalized = str(email or "").strip().lower()
    if not normalized:
        raise ValueError("Email is required.")
    current = get_user_admin_state(normalized)
    current.update({key: value for key, value in updates.items() if key in current})
    current["updated_at"] = int(time.time())
    init_storage()
    with _LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO user_admin_state (email, is_active, requires_reverify, otp_bypass_allowed, real_mode_enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    is_active = excluded.is_active,
                    requires_reverify = excluded.requires_reverify,
                    otp_bypass_allowed = excluded.otp_bypass_allowed,
                    real_mode_enabled = excluded.real_mode_enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized,
                    1 if current["is_active"] else 0,
                    1 if current["requires_reverify"] else 0,
                    1 if current["otp_bypass_allowed"] else 0,
                    1 if current["real_mode_enabled"] else 0,
                    current["updated_at"],
                ),
            )
            connection.commit()
        finally:
            connection.close()
    return current


def list_user_admin_states():
    init_storage()
    with _LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                "SELECT email, is_active, requires_reverify, otp_bypass_allowed, real_mode_enabled, updated_at FROM user_admin_state ORDER BY email ASC"
            ).fetchall()
        finally:
            connection.close()
    return [
        {
            "email": row["email"],
            "is_active": bool(row["is_active"]),
            "requires_reverify": bool(row["requires_reverify"]),
            "otp_bypass_allowed": bool(row["otp_bypass_allowed"]),
            "real_mode_enabled": bool(row["real_mode_enabled"]),
            "updated_at": int(row["updated_at"] or 0),
        }
        for row in rows
    ]


def record_payment(email, amount_cents, currency, paid_at, payment_intent_id, checkout_session_id="", subscription_id="", status="paid"):
    normalized = str(email or "").strip().lower()
    if not normalized or not payment_intent_id:
        return
    init_storage()
    with _LOCK:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT OR IGNORE INTO payment_events
                (email, amount_cents, currency, paid_at, payment_intent_id, checkout_session_id, subscription_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    int(amount_cents or 0),
                    str(currency or "usd").strip().lower() or "usd",
                    int(paid_at or time.time()),
                    str(payment_intent_id or "").strip(),
                    str(checkout_session_id or "").strip(),
                    str(subscription_id or "").strip(),
                    str(status or "paid").strip().lower() or "paid",
                ),
            )
            connection.commit()
        finally:
            connection.close()


def list_payments():
    init_storage()
    with _LOCK:
        connection = _connect()
        try:
            rows = connection.execute(
                """
                SELECT id, email, amount_cents, currency, paid_at, payment_intent_id, checkout_session_id, subscription_id, status
                FROM payment_events
                ORDER BY paid_at DESC, id DESC
                """
            ).fetchall()
        finally:
            connection.close()
    return [
        {
            "id": int(row["id"]),
            "email": row["email"],
            "amount_cents": int(row["amount_cents"] or 0),
            "currency": row["currency"],
            "paid_at": int(row["paid_at"] or 0),
            "payment_intent_id": row["payment_intent_id"],
            "checkout_session_id": row["checkout_session_id"],
            "subscription_id": row["subscription_id"],
            "status": row["status"],
        }
        for row in rows
    ]


def payment_stats():
    payments = list_payments()
    paid_emails = {payment["email"] for payment in payments}
    return {
        "total_payments": len(payments),
        "paid_user_count": len(paid_emails),
        "total_amount_cents": sum(payment["amount_cents"] for payment in payments),
    }
