"""Outgoing e-mail. Sending happens in a Celery task AFTER the request, never inside the
business transaction. In the test environment messages are captured in `outbox`."""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

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


def deliver(email: Email) -> None:
    """Queue an e-mail. Never raises: a mail outage must not fail the user's request."""
    if get_settings().app_env == "test":
        outbox.append(email)
        return
    try:
        from app.tasks.celery_app import send_email_task

        send_email_task.delay(email.to, email.subject, email.body)
    except Exception:
        logger.exception("Could not queue e-mail")


async def deliver_direct(email: Email) -> None:
    """Send immediately through SMTP (used by flows that must not depend on Celery)."""
    if get_settings().app_env == "test":
        outbox.append(email)
        return
    try:
        await to_thread.run_sync(send_now, email)
    except Exception:
        # Do not log the message body: it may contain a one-time password.
        logger.exception("Could not send e-mail directly")
