from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from ..config import get_settings


log = logging.getLogger(__name__)


def email_delivery_ready() -> bool:
    cfg = get_settings()
    return cfg.ACCOUNT_EMAIL_DELIVERY == "log" or bool(cfg.SMTP_HOST)


async def send_account_email(to_email: str, subject: str, body: str) -> None:
    cfg = get_settings()
    if cfg.ACCOUNT_EMAIL_DELIVERY == "log":
        log.warning("Development account email to %s: %s\n%s", to_email, subject, body)
        return
    if not cfg.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is required for account email delivery.")

    message = EmailMessage()
    message["From"] = f"{cfg.SMTP_FROM_NAME} <{cfg.SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    await aiosmtplib.send(
        message,
        hostname=cfg.SMTP_HOST,
        port=cfg.SMTP_PORT,
        username=cfg.SMTP_USERNAME or None,
        password=cfg.SMTP_PASSWORD or None,
        start_tls=cfg.SMTP_START_TLS,
        timeout=15,
    )
