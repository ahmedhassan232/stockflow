"""Fixed-window counters in Redis. Fails CLOSED: if Redis is unavailable, protected
endpoints answer 503 instead of silently running unprotected."""

import hashlib
import logging

from fastapi import Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimitedError, ServiceUnavailableError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)
PREFIX = "stockflow:rl:"


def _key(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
    return f"{PREFIX}{parts[0]}:{digest}"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def hit(redis: Redis, scope: str, identity: str, *, limit: int, window: int) -> None:
    """Count one event; raise 429 once `limit` is exceeded inside `window` seconds."""
    key = _key(scope, identity)
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window)
    except RedisError as exc:
        logger.exception("Rate limiter unavailable")
        raise ServiceUnavailableError() from exc
    if count > limit:
        raise RateLimitedError()


async def current(redis: Redis, scope: str, identity: str) -> int:
    try:
        return int(await redis.get(_key(scope, identity)) or 0)
    except RedisError as exc:
        logger.exception("Rate limiter unavailable")
        raise ServiceUnavailableError() from exc


async def reset(redis: Redis, scope: str, identity: str) -> None:
    try:
        await redis.delete(_key(scope, identity))
    except RedisError:
        logger.exception("Rate limiter unavailable")


async def auth_rate_limit(
    request: Request,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> None:
    """Per-IP throttle for all unauthenticated auth endpoints."""
    await hit(
        redis, "auth-ip", client_ip(request), limit=settings.auth_rate_limit_per_minute, window=60
    )
