import os
import time
from urllib.parse import urlencode

import aiohttp

from config import settings


STRIPE_API_BASE = "https://api.stripe.com/v1"
SUBSCRIPTION_PRICE_CENTS = int(round(float(settings.REAL_MODE_FEE or 29) * 100))
SUBSCRIPTION_CURRENCY = "usd"


def stripe_secret_key():
    return (
        os.getenv("STRIPE_SECRET")
        or os.getenv("STRIPE_SECRET_KEY")
        or os.getenv("STRIPE_TEST_SECRET")
        or os.getenv("STRIPE_TEST_SECRET_KEY")
        or ""
    ).strip()


def stripe_publishable_key():
    return (
        os.getenv("STRIPE_KEY")
        or os.getenv("STRIPE_PUBLISHABLE_KEY")
        or os.getenv("STRIPE_TEST_KEY")
        or os.getenv("STRIPE_TEST_PUBLISHABLE_KEY")
        or ""
    ).strip()


def stripe_configured():
    return bool(stripe_secret_key())


async def _stripe_request(method, path, data=None, params=None):
    secret = stripe_secret_key()
    if not secret:
        raise RuntimeError("Stripe secret key is missing in .env.")

    headers = {
        "Authorization": f"Bearer {secret}",
    }
    kwargs = {"headers": headers}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        kwargs["data"] = urlencode(data, doseq=True)
    if params is not None:
        kwargs["params"] = params

    async with aiohttp.ClientSession() as session:
        async with session.request(method, f"{STRIPE_API_BASE}{path}", **kwargs) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                message = (
                    ((payload or {}).get("error") or {}).get("message")
                    or "Stripe request failed."
                )
                raise RuntimeError(message)
            return payload


def normalize_subscription(subscription):
    data = subscription or {}
    period_end = int(((data.get("current_period_end") or 0)))
    status = str(data.get("status") or "inactive").strip().lower()
    return {
        "subscription_id": str(data.get("id") or "").strip(),
        "status": status,
        "current_period_end": period_end,
        "current_period_start": int(data.get("current_period_start") or 0),
        "cancel_at_period_end": bool(data.get("cancel_at_period_end", False)),
        "last_synced_at": int(time.time()),
    }


def extract_payment_event(session_payload):
    data = session_payload or {}
    subscription_obj = data.get("subscription") or {}
    latest_invoice = (subscription_obj.get("latest_invoice") or {}) if isinstance(subscription_obj, dict) else {}
    payment_intent = latest_invoice.get("payment_intent") or data.get("payment_intent") or {}
    if not isinstance(payment_intent, dict):
        payment_intent = {"id": str(payment_intent or "").strip()}
    return {
        "amount_cents": int(data.get("amount_total") or 0),
        "currency": str(data.get("currency") or SUBSCRIPTION_CURRENCY).strip().lower(),
        "payment_intent_id": str(payment_intent.get("id") or "").strip(),
        "paid_at": int(time.time()),
        "checkout_session_id": str(data.get("id") or "").strip(),
        "subscription_id": str((subscription_obj.get("id") if isinstance(subscription_obj, dict) else subscription_obj) or "").strip(),
    }


async def create_checkout_session(email, success_url, cancel_url, customer_id=""):
    amount_label = f"${float(settings.REAL_MODE_FEE or 29):.2f}"
    payload = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "payment_method_types[]": "card",
        "line_items[0][price_data][currency]": SUBSCRIPTION_CURRENCY,
        "line_items[0][price_data][product_data][name]": "Scalper Bot Real Account Subscription",
        "line_items[0][price_data][product_data][description]": f"{amount_label} monthly subscription for real Binance mode",
        "line_items[0][price_data][unit_amount]": str(SUBSCRIPTION_PRICE_CENTS),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][quantity]": "1",
        "allow_promotion_codes": "false",
        "subscription_data[metadata][plan]": "real_account_monthly",
        "metadata[email]": email,
    }
    if customer_id:
        payload["customer"] = customer_id
    else:
        payload["customer_email"] = email
    return await _stripe_request("POST", "/checkout/sessions", data=payload)


async def fetch_checkout_session(session_id):
    return await _stripe_request(
        "GET",
        f"/checkout/sessions/{session_id}",
        params=[
            ("expand[]", "subscription"),
            ("expand[]", "subscription.latest_invoice.payment_intent"),
            ("expand[]", "customer"),
        ],
    )


async def fetch_subscription(subscription_id):
    return await _stripe_request(
        "GET",
        f"/subscriptions/{subscription_id}",
        params=[("expand[]", "latest_invoice.payment_intent")],
    )
