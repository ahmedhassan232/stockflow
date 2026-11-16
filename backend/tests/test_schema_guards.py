"""Guards that fail the build when a FUTURE table forgets a tenant-isolation rule."""

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.db.models  # noqa: F401
from app.db.base import Base

# Tables that intentionally have no tenant_id. Adding to this list needs a review.
GLOBAL_TABLES = {
    "alembic_version",
    "tenants",
    "users",
    "auth_sessions",
    "refresh_tokens",
    "password_reset_tokens",
    "permissions",
    "platform_audit_logs",  # operator log; the app role has no privilege on it at all
}


def _sync(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def owner_conn(settings):
    with psycopg.connect(_sync(settings.migration_database_url)) as conn:
        yield conn


def test_every_table_is_tenant_owned_or_explicitly_global(owner_conn):
    rows = owner_conn.execute(
        """
        SELECT c.relname,
               EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
                          AND a.attnotnull AND NOT a.attisdropped) AS has_tenant
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r'
        """
    ).fetchall()
    unclassified = [
        name for name, has_tenant in rows if not has_tenant and name not in GLOBAL_TABLES
    ]
    assert unclassified == [], f"tables without NOT NULL tenant_id: {unclassified}"


def test_every_tenant_table_has_forced_rls_policy_and_composite_key(owner_conn):
    rows = owner_conn.execute(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid
                        AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app_current_tenant_id()%'
                        AND pg_get_expr(p.polwithcheck, p.polrelid)
                            LIKE '%app_current_tenant_id()%') AS has_policy,
               EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'u'
                        AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
                               FROM pg_attribute a
                              WHERE a.attrelid = c.oid AND a.attnum = ANY (k.conkey))
                            = ARRAY['id', 'tenant_id']) AS has_composite_key
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r'
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'tenant_id')
        """
    ).fetchall()
    assert len(rows) >= 4
    for name, enabled, forced, has_policy, has_key in rows:
        assert enabled and forced, f"{name}: RLS must be ENABLED and FORCED"
        assert has_policy, f"{name}: missing tenant_isolation policy (USING + WITH CHECK)"
        assert has_key, f"{name}: missing UNIQUE (tenant_id, id)"


def test_tenants_table_itself_is_protected(owner_conn):
    enabled, forced = owner_conn.execute(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'tenants'"
    ).fetchone()
    assert enabled and forced


def test_schema_owner_is_also_subject_to_rls(owner_conn):
    """FORCE RLS: even the migration role sees no business rows without a context."""
    assert owner_conn.execute("SELECT count(*) FROM branches").fetchone()[0] == 0


def test_fks_to_tenant_tables_are_composite(owner_conn):
    """Any FK pointing at a tenant-owned table must include tenant_id on both sides."""
    bad = owner_conn.execute(
        """
        SELECT k.conname
          FROM pg_constraint k
          JOIN pg_class target ON target.oid = k.confrelid
         WHERE k.contype = 'f'
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = target.oid AND a.attname = 'tenant_id')
           AND NOT EXISTS (SELECT 1 FROM pg_attribute a
                            WHERE a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)
                              AND a.attname = 'tenant_id')
        """
    ).fetchall()
    assert bad == []


def test_models_and_migrations_do_not_drift(settings):
    engine = create_engine(settings.migration_database_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"run `alembic revision --autogenerate`: {diff}"
