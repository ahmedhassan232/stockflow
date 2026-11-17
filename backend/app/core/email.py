"""Outgoing e-mail. Password-reset codes use the HTTPS provider API so they work
on hosts that block outbound SMTP. In tests, messages are captured in outbox.
"""

import json
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from anyio import to_thread

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


outbox: list[Email] = []


def send_now(email: Email) -> None:
    """Send through the legacy SMTP transport (used by the Celery mail task)."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, email.to, email.subject
    msg.set_content(email.body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        if s.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password)
        smtp.send_message(msg)


def send_via_resend(email: Email) -> None:
    """Send one transactional message using Resend HTTPS API."""
    s = get_settings()
    if not s.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")
    payload = json.dumps(
        {"from": s.resend_from, "to": [email.to], "subject": email.subject, "text": email.body}
    ).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {s.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Resend API returned HTTP {response.status}")
    except HTTPError as exc:
        # Read only the provider error, never the request payload (which contains the OTP).
        # Redact email addresses because Resend may echo the account address in its message.
        try:
            provider_error = json.loads(exc.read(2048).decode("utf-8"))
            detail = str(provider_error.get("message") or provider_error.get("name") or "No error detail")
        except Exception:
            detail = "No readable error detail"
        detail = re.sub(r"[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}", "[redacted email]", detail)
        raise RuntimeError(f"Resend API returned HTTP {exc.code}: {detail}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Resend HTTPS request failed: {type(exc).__name__}") from None


def deliver(email: Email) -> None:
    """Queue an e-mail. Never raises: a mail outage must not fail the user request."""
    if get_settings().app_env == "test":
        outbox.append(email)
        return
    try:
        from app.tasks.celery_app import send_email_task

        send_email_task.delay(email.to, email.subject, email.body)
    except Exception:
        logger.exception("Could not queue e-mail")


async def deliver_direct(email: Email) -> None:
    """Send immediately through Resend HTTPS, falling back to SMTP without an API key."""
    if get_settings().app_env == "test":
        outbox.append(email)
        return
    try:
        sender = send_via_resend if get_settings().resend_api_key else send_now
        await to_thread.run_sync(sender, email)
    except Exception:
        # Do not log the message body: it may contain a one-time password.
        logger.exception("Could not send e-mail directly")
