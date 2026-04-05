import asyncio
import os
import socket
import smtplib
import ssl
from email.message import EmailMessage


def _smtp_bool(name, default=False):
    value = str(os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


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


def _is_render_runtime():
    return bool(
        str(os.getenv("RENDER") or "").strip()
        or str(os.getenv("RENDER_SERVICE_ID") or "").strip()
        or str(os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
    )


def format_smtp_delivery_error(exc, cfg=None):
    smtp_cfg = cfg or SMTPConfig()
    text = " ".join(str(exc).split())
    lowered = text.lower()
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
                "Use a paid Render instance or switch email delivery to an HTTP-based provider API."
            )

    if isinstance(exc, socket.gaierror):
        return f"SMTP host lookup failed for {smtp_cfg.host}. Please check MAIL_HOST."
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed. Please verify MAIL_USERNAME and MAIL_PASSWORD."
    if isinstance(exc, TimeoutError) or "timed out" in lowered:
        return f"SMTP connection to {smtp_cfg.host}:{smtp_cfg.port} timed out."
    if "network is unreachable" in lowered:
        return f"SMTP connection to {smtp_cfg.host}:{smtp_cfg.port} could not be reached from this server."
    return text or "SMTP delivery failed."


def _build_message(to_email, subject, text_body, html_body=""):
    message = EmailMessage()
    cfg = SMTPConfig()
    message["Subject"] = subject
    message["From"] = f"{cfg.from_name} <{cfg.from_email}>" if cfg.from_name else cfg.from_email
    message["To"] = to_email
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
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


async def send_registration_code(to_email, code):
    code_text = str(code or "").strip()
    if not code_text:
        raise ValueError("Verification code is required.")
    message = _build_message(
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
    await asyncio.to_thread(_send_message_sync, message)


async def send_access_code(to_email, code, title="Verify your account", subtitle="Use this 4-digit code to continue securely."):
    code_text = str(code or "").strip()
    if not code_text:
        raise ValueError("Verification code is required.")
    message = _build_message(
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
    await asyncio.to_thread(_send_message_sync, message)
