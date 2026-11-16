"""Test bootstrap. Uses a REAL PostgreSQL database and a real Redis (no mocks):
RLS, transactions and locking cannot be verified against substitutes."""

import os

# Must run before any `app` import so Settings picks the test database.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["MIGRATION_DATABASE_URL"] = os.environ["TEST_MIGRATION_DATABASE_URL"]
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-not-used-anywhere-else-0123456789"
os.environ["COOKIE_SECURE"] = "false"
os.environ["COOKIE_SAMESITE"] = "lax"
os.environ["ARGON2_TIME_COST"] = "1"  # fast hashing in tests only
os.environ["ARGON2_MEMORY_KIB"] = "1024"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["FRONTEND_URL"] = "http://testserver"

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    """Rebuild the test schema from migrations: also proves downgrade/upgrade work."""
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
async def two_companies():
    """Two independent companies provisioned through the real service."""
    from tests.factories import create_company

    return await create_company("Alpha Trading"), await create_company("Beta Stores")


@pytest.fixture(autouse=True)
async def _clean_rate_limits_and_outbox():
    from app.core import email
    from app.core.rate_limit import PREFIX
    from app.core.redis import get_redis

    redis = get_redis()
    keys = [k async for k in redis.scan_iter(f"{PREFIX}*")]
    if keys:
        await redis.delete(*keys)
    email.outbox.clear()
    yield
