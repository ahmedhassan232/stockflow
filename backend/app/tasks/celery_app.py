"""Celery application (worker + beat).

Background tasks are for work that may run *after* a business transaction (emails,
low-stock scans, heavy exports). Anything that must be atomic with a sale, receipt or
transfer stays inside the request transaction and is never delegated to Celery.
"""

from datetime import UTC, datetime

import redis
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "stockflow",
    broker=settings.celery_broker_url or settings.redis_url,
    backend=settings.celery_result_backend or settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "system-heartbeat": {"task": "system.heartbeat", "schedule": 60.0},
        "inventory-low-stock-scan": {"task": "inventory.low_stock_scan", "schedule": 900.0},
        # 05:00 UTC = start of the working day in Egypt / the Gulf
        "inventory-low-stock-digest": {
            "task": "inventory.low_stock_digest",
            "schedule": crontab(hour=5, minute=0),
        },
    },
)

HEARTBEAT_KEY = "stockflow:celery:heartbeat"


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="system.heartbeat")
def heartbeat() -> str:
    """Scheduled by beat; proves the beat → broker → worker pipeline works."""
    now = datetime.now(UTC).isoformat()
    client = redis.Redis.from_url(settings.redis_url)
    try:
        client.set(HEARTBEAT_KEY, now, ex=300)
    finally:
        client.close()
    return now


@celery_app.task(
    name="email.send", autoretry_for=(OSError,), retry_backoff=True, max_retries=5, acks_late=True
)
def send_email_task(to: str, subject: str, body: str) -> None:
    from app.core.email import Email, send_now

    send_now(Email(to=to, subject=subject, body=body))


@celery_app.task(name="inventory.low_stock_scan")
def low_stock_scan_task() -> dict[str, int]:
    """Every 15 minutes: raise a notification for each item at or below its minimum."""
    from app.tasks.low_stock import run_scan

    return run_scan()


@celery_app.task(name="inventory.low_stock_digest")
def low_stock_digest_task() -> dict[str, int]:
    """Daily e-mail listing low items to the people allowed to see stock."""
    from app.tasks.low_stock import run_digest

    return run_digest()
