"""Async engine + request-scoped session.

Each request gets one session wrapped in ONE transaction. From Phase 2 the tenant
context is applied with `set_config('app.tenant_id', ..., true)`, i.e. transaction-local,
so it is discarded at COMMIT/ROLLBACK and can never leak to the next request that
borrows the same pooled connection.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        s = get_settings()
        kwargs: dict = {"pool_pre_ping": True}
        if s.app_env == "test":
            kwargs["poolclass"] = NullPool
        else:
            kwargs.update(
                pool_size=s.db_pool_size,
                max_overflow=s.db_max_overflow,
                pool_timeout=s.db_pool_timeout,
                pool_recycle=1800,
            )
        _engine = create_async_engine(s.database_url, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None  # noqa: S101
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one unit of work per request – commit on success, roll back on
    any error. A service may commit explicitly in the rare case where a security fact must
    survive the error it is about to raise (e.g. revoking a session on token reuse)."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
