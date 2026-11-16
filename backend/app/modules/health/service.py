import asyncio
import logging
import time
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.modules.health.schemas import (
    ComponentHealth,
    DatabaseHealth,
    LivenessData,
    ReadinessData,
)

logger = logging.getLogger(__name__)

_DB_PROBE = text(
    """
    SELECT current_setting('server_version')                         AS server_version,
           (SELECT version_num FROM alembic_version LIMIT 1)         AS schema_revision,
           (SELECT NOT (rolsuper OR rolbypassrls)
              FROM pg_roles WHERE rolname = current_user)            AS rls_enforced
    """
)


class HealthService:
    def __init__(self, settings: Settings, engine: AsyncEngine, redis: Redis) -> None:
        self._settings = settings
        self._engine = engine
        self._redis = redis

    def liveness(self) -> LivenessData:
        s = self._settings
        return LivenessData(
            service=s.app_name, version=s.app_version, environment=s.app_env, time=datetime.now(UTC)
        )

    async def readiness(self) -> ReadinessData:
        database, redis = await asyncio.gather(self._check_database(), self._check_redis())
        overall = "ok" if database.status == "ok" and redis.status == "ok" else "error"
        return ReadinessData(status=overall, database=database, redis=redis, time=datetime.now(UTC))

    async def _check_database(self) -> DatabaseHealth:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._settings.health_check_timeout_seconds):
                async with self._engine.connect() as conn:
                    row = (await conn.execute(_DB_PROBE)).one()
        except Exception:
            # Full error goes to the log only; clients get a generic message.
            logger.exception("Database health check failed")
            return DatabaseHealth(status="error", detail="Database is unreachable or not migrated")

        latency = round((time.perf_counter() - started) * 1000, 2)
        if not row.rls_enforced and self._settings.is_production:
            return DatabaseHealth(
                status="error",
                latency_ms=latency,
                rls_enforced_for_role=False,
                detail="Runtime database role must not be able to bypass row level security",
            )
        return DatabaseHealth(
            status="ok",
            latency_ms=latency,
            server_version=row.server_version.split(" ")[0],
            schema_revision=row.schema_revision,
            rls_enforced_for_role=bool(row.rls_enforced),
        )

    async def _check_redis(self) -> ComponentHealth:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._settings.health_check_timeout_seconds):
                await self._redis.ping()
        except Exception:
            logger.exception("Redis health check failed")
            return ComponentHealth(status="error", detail="Redis is unreachable")
        return ComponentHealth(
            status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2)
        )
