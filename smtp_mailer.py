import asyncio
import os
import socket
import smtplib
import ssl
from email.message import EmailMessage

import aiohttp


def _smtp_bool(name, default=False):
    value = str(os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _is_render_runtime():
    return bool(
        str(os.getenv("RENDER") or "").strip()
        or str(os.getenv("RENDER_SERVICE_ID") or "").strip()
        or str(os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
    )


class SMTPConfig:
    def __init__(self):
        self.host = (
            os.getenv("SMTP_HOST")
            or os.getenv("MAIL_HOST")
            or os.getenv("MAIL_SERVER")
            or ""
        ).strip()
        self.port = int(
            os.getenv("SMTP_PORT")
            or os.getenv("MAIL_PORT")
            or "587"
        )
        self.username = (
            os.getenv("SMTP_USERNAME")
            or os.getenv("SMTP_USER")
            or os.getenv("MAIL_USERNAME")
            or ""
        ).strip()
        self.password = (
            os.getenv("SMTP_PASSWORD")
            or os.getenv("SMTP_PASS")
            or os.getenv("MAIL_PASSWORD")
            or ""
        ).strip()
        self.from_email = (
            os.getenv("SMTP_FROM_EMAIL")
            or os.getenv("MAIL_FROM_ADDRESS")
            or self.username
        ).strip()
        self.from_name = (
            os.getenv("SMTP_FROM_NAME")
            or os.getenv("MAIL_FROM_NAME")
            or "Scalper Bot"
        ).strip()
        encryption = str(os.getenv("MAIL_ENCRYPTION") or "").strip().lower()
        self.use_ssl = _smtp_bool("SMTP_SSL") or _smtp_bool("MAIL_SSL") or encryption == "ssl"
        self.use_tls = _smtp_bool("SMTP_TLS", default=(encryption == "tls" or not self.use_ssl)) or encryption == "tls"

    def is_configured(self):
        return bool(self.host and self.port and self.from_email)


class MailDeliveryConfig:
    def __init__(self):
        self.provider = str(
            os.getenv("MAIL_PROVIDER")
            or os.getenv("EMAIL_PROVIDER")
            or "auto"
        ).strip().lower()
        self.from_email = (
            os.getenv("MAIL_FROM_ADDRESS")
            or os.getenv("SMTP_FROM_EMAIL")
            or os.getenv("RESEND_FROM_EMAIL")
            or os.getenv("BREVO_FROM_EMAIL")
            or os.getenv("MAIL_USERNAME")
            or ""
        ).strip()
        self.from_name = (
            os.getenv("MAIL_FROM_NAME")
            or os.getenv("SMTP_FROM_NAME")
            or "Scalper Bot"
        ).strip()
        self.resend_api_key = (
            os.getenv("RESEND_API_KEY")
            or os.getenv("RESEND_KEY")
            or ""
        ).strip()
        self.brevo_api_key = (
            os.getenv("BREVO_API_KEY")
            or os.getenv("SENDINBLUE_API_KEY")
            or ""
        ).strip()
        self.smtp = SMTPConfig()

    def selected_provider(self):
        if self.provider in {"resend", "brevo", "smtp"}:
            return self.provider
        if self.resend_api_key:
            return "resend"
        if self.brevo_api_key:
            return "brevo"
        return "smtp"

    def is_configured(self):
        provider = self.selected_provider()
        if provider == "resend":
            return bool(self.resend_api_key and self.from_email)
        if provider == "brevo":
            return bool(self.brevo_api_key and self.from_email)
        return self.smtp.is_configured()


def format_mail_delivery_error(exc, cfg=None):
    mail_cfg = cfg or MailDeliveryConfig()
    provider = mail_cfg.selected_provider()
    text = " ".join(str(exc).split())
    lowered = text.lower()

    if provider == "resend":
        if "401" in lowered or "403" in lowered:
            return "Resend authentication failed. Please verify RESEND_API_KEY."
        if "domain" in lowered and ("verify" in lowered or "not found" in lowered):
            return "Resend rejected the sender domain. Verify your sending domain or use a valid RESEND_FROM_EMAIL."
        return text or "Resend email delivery failed."

    if provider == "brevo":
        if "401" in lowered or "403" in lowered:
            return "Brevo authentication failed. Please verify BREVO_API_KEY."
        if "sender" in lowered and ("invalid" in lowered or "unauthorized" in lowered):
            return "Brevo rejected the sender email. Verify MAIL_FROM_ADDRESS or BREVO_FROM_EMAIL in your Brevo sender settings."
        return text or "Brevo email delivery failed."

    smtp_cfg = mail_cfg.smtp
    blocked_ports = {25, 465, 587}
    if _is_render_runtime() and smtp_cfg.port in blocked_ports:
        if (
            "network is unreachable" in lowered
            or "connection refused" in lowered
            or "timed out" in lowered
            or isinstance(exc, OSError)
        ):
            return (
                f"SMTP delivery failed because this Render service cannot reach outbound SMTP on port {smtp_cfg.port}. "
                "Render free web services block ports 25, 465, and 587. "
                "Set MAIL_PROVIDER=resend or MAIL_PROVIDER=brevo and add that provider API key, or move to a paid Render instance."
            )
    if isinstance(exc, socket.gaierror):
        return f"SMTP host lookup failed for {smtp_cfg.host}. Please check MAIL_HOST."
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed. Please verify MAIL_USERNAME and MAIL_PASSWORD."
    if isinstance(exc, TimeoutError) or "timed out" in lowered:
        return f"SMTP connection to {smtp_cfg.host}:{smtp_cfg.port} timed out."
    if "network is unreachable" in lowered:
        return f"SMTP connection to {smtp_cfg.host}:{smtp_cfg.port} could not be reached from this server."
    return text or "Mail delivery failed."


def format_smtp_delivery_error(exc, cfg=None):
    return format_mail_delivery_error(exc, cfg=cfg)


def _build_message_payload(to_email, subject, text_body, html_body=""):
    cfg = MailDeliveryConfig()
    return {
        "to_email": to_email,
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
        "from_email": cfg.from_email,
        "from_name": cfg.from_name,
    }


def _build_smtp_message(payload):
    message = EmailMessage()
    message["Subject"] = payload["subject"]
    from_email = payload["from_email"]
    from_name = payload["from_name"]
    message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    message["To"] = payload["to_email"]
    message.set_content(payload["text_body"])
    if payload["html_body"]:
        message.add_alternative(payload["html_body"], subtype="html")
    return message


def _send_message_sync(message):
    cfg = SMTPConfig()
    if not cfg.is_configured():
        raise RuntimeError("SMTP is not configured in .env.")

    context = ssl.create_default_context()
    if cfg.use_ssl:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=20, context=context) as server:
            if cfg.username:
                server.login(cfg.username, cfg.password)
            server.send_message(message)
        return

    with smtplib.SMTP(cfg.host, cfg.port, timeout=20) as server:
        server.ehlo()
        if cfg.use_tls:
            server.starttls(context=context)
            server.ehlo()
        if cfg.username:
            server.login(cfg.username, cfg.password)
        server.send_message(message)


async def _send_with_resend(payload, cfg):
    headers = {
        "Authorization": f"Bearer {cfg.resend_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "from": f"{payload['from_name']} <{payload['from_email']}>" if payload["from_name"] else payload["from_email"],
        "to": [payload["to_email"]],
        "subject": payload["subject"],
        "text": payload["text_body"],
        "html": payload["html_body"] or payload["text_body"],
    }
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://api.resend.com/emails", headers=headers, json=body) as response:
            result_text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Resend API error {response.status}: {result_text}")


async def _send_with_brevo(payload, cfg):
    headers = {
        "api-key": cfg.brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "sender": {
            "name": payload["from_name"],
            "email": payload["from_email"],
        },
        "to": [{"email": payload["to_email"]}],
        "subject": payload["subject"],
        "textContent": payload["text_body"],
        "htmlContent": payload["html_body"] or payload["text_body"],
    }
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://api.brevo.com/v3/smtp/email", headers=headers, json=body) as response:
            result_text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Brevo API error {response.status}: {result_text}")


async def send_message(to_email, subject, text_body, html_body=""):
    payload = _build_message_payload(to_email, subject, text_body, html_body)
    cfg = MailDeliveryConfig()
    if not cfg.is_configured():
        raise RuntimeError(
            "Mail delivery is not configured. Set MAIL_PROVIDER=resend with RESEND_API_KEY, "
            "or MAIL_PROVIDER=brevo with BREVO_API_KEY, or configure SMTP."
        )

    provider = cfg.selected_provider()
    if provider == "resend":
        await _send_with_resend(payload, cfg)
        return
    if provider == "brevo":
        await _send_with_brevo(payload, cfg)
        return

    message = _build_smtp_message(payload)
    await asyncio.to_thread(_send_message_sync, message)


async def send_registration_code(to_email, code):
    code_text = str(code or "").strip()
    if not code_text:
        raise ValueError("Verification code is required.")
    await send_message(
        to_email=to_email,
        subject="Your Scalper Bot verification code",
        text_body=(
            f"Your 4-digit verification code is {code_text}. "
            "It expires in 5 minutes. If you did not request this, please ignore this email."
        ),
        html_body=(
            "<div style=\"font-family:Segoe UI,Arial,sans-serif;padding:24px;color:#0f172a;\">"
            "<h2 style=\"margin:0 0 12px;\">Verify your account</h2>"
            "<p style=\"margin:0 0 16px;\">Use this 4-digit code to finish your registration.</p>"
            f"<div style=\"font-size:32px;font-weight:700;letter-spacing:8px;color:#2563eb;\">{code_text}</div>"
            "<p style=\"margin:16px 0 0;\">This code expires in 5 minutes.</p>"
            "</div>"
        ),
    )


async def send_access_code(to_email, code, title="Verify your account", subtitle="Use this 4-digit code to continue securely."):
    code_text = str(code or "").strip()
    if not code_text:
        raise ValueError("Verification code is required.")
    await send_message(
        to_email=to_email,
        subject=f"{title} - Scalper Bot",
        text_body=(
            f"Your 4-digit verification code is {code_text}. "
            "It expires in 5 minutes. If you did not request this, please ignore this email."
        ),
        html_body=(
            "<div style=\"font-family:Segoe UI,Arial,sans-serif;padding:24px;color:#0f172a;\">"
            f"<h2 style=\"margin:0 0 12px;\">{title}</h2>"
            f"<p style=\"margin:0 0 16px;\">{subtitle}</p>"
            f"<div style=\"font-size:32px;font-weight:700;letter-spacing:8px;color:#2563eb;\">{code_text}</div>"
            "<p style=\"margin:16px 0 0;\">This code expires in 5 minutes.</p>"
            "</div>"
        ),
    )
