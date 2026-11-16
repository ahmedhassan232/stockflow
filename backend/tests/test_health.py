import psycopg
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.redis import get_redis
from app.db.session import get_engine

LIVE = "/api/v1/health/live"
READY = "/api/v1/health/ready"


async def test_liveness_returns_envelope(client):
    r = await client.get(LIVE)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["environment"] == "test"
    assert r.headers["x-request-id"]


async def test_readiness_reports_real_postgres_and_redis(client):
    r = await client.get(READY)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "ok"
    assert data["database"]["status"] == "ok"
    assert data["database"]["server_version"].startswith("17")
    assert data["database"]["schema_revision"] == "0008"
    assert data["redis"]["status"] == "ok"


async def test_runtime_role_cannot_bypass_rls(client):
    data = (await client.get(READY)).json()["data"]
    assert data["database"]["rls_enforced_for_role"] is True


async def test_readiness_is_503_when_database_is_down(app, client):
    dead = create_async_engine(
        "postgresql+psycopg://nobody:secret-pw@127.0.0.1:1/none", poolclass=NullPool
    )
    app.dependency_overrides[get_engine] = lambda: dead
    r = await client.get(READY)
    assert r.status_code == 503
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["details"]["database"]["status"] == "error"
    assert body["error"]["details"]["redis"]["status"] == "ok"
    # Connection details / driver errors must never reach the client.
    assert "secret-pw" not in r.text and "127.0.0.1" not in r.text and "psycopg" not in r.text


async def test_readiness_is_503_when_redis_is_down(app, client):
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.5)
    app.dependency_overrides[get_redis] = lambda: dead
    r = await client.get(READY)
    assert r.status_code == 503
    assert r.json()["error"]["details"]["redis"]["status"] == "error"
    await dead.aclose()


async def test_unknown_route_uses_error_envelope(client):
    r = await client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {
        "success": False,
        "error": {"code": "RESOURCE_NOT_FOUND", "message": "Not Found"},
    }


async def test_cors_allows_only_listed_origins(client, settings):
    allowed = settings.cors_origin_list[0]
    ok = await client.get(LIVE, headers={"Origin": allowed})
    assert ok.headers["access-control-allow-origin"] == allowed
    denied = await client.get(LIVE, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


async def test_request_id_is_echoed_or_replaced(client):
    good = await client.get(LIVE, headers={"X-Request-ID": "abc-12345678"})
    assert good.headers["x-request-id"] == "abc-12345678"
    bad = await client.get(LIVE, headers={"X-Request-ID": 'x"><script>'})
    assert bad.headers["x-request-id"] != 'x"><script>'


def _sync_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def test_runtime_role_cannot_run_ddl(settings):
    """The API role may use tables but can never create or alter schema objects."""
    with psycopg.connect(_sync_url(settings.database_url)) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE should_not_exist (id int)")


def test_tenant_context_is_transaction_local(settings):
    """Foundation for RLS: the tenant GUC vanishes at COMMIT, so a pooled connection
    can never carry one request's tenant into the next request."""
    tenant = "11111111-1111-1111-1111-111111111111"
    with psycopg.connect(_sync_url(settings.database_url)) as conn:
        assert conn.execute("SELECT app_current_tenant_id()").fetchone()[0] is None
        conn.commit()
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        assert str(conn.execute("SELECT app_current_tenant_id()").fetchone()[0]) == tenant
        conn.commit()
        assert conn.execute("SELECT app_current_tenant_id()").fetchone()[0] is None


def test_celery_ping_task_runs():
    from app.tasks.celery_app import celery_app, ping

    celery_app.conf.task_always_eager = True
    try:
        assert ping.delay().get(timeout=5) == "pong"
    finally:
        celery_app.conf.task_always_eager = False
