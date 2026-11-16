"""Database foundation: extensions, tenant-context helpers, runtime-role privileges.

No business tables yet (they arrive in Phase 2). This revision installs everything
those tables rely on:

* citext / pg_trgm                 – case-insensitive e-mails, fast name/SKU search.
* app_current_tenant_id()          – reads the transaction-local `app.tenant_id` GUC;
                                     returns NULL when unset, so RLS policies written as
                                     `tenant_id = app_current_tenant_id()` deny by default.
* set_updated_at()                 – trigger function maintaining `updated_at`.
* default privileges               – every future table/sequence created by the owner is
                                     automatically usable (DML only) by the runtime role.
                                     The runtime role never owns tables and cannot DDL.

Revision ID: 0001
Revises:
"""

import re

from alembic import op

from app.core.config import get_settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _runtime_role() -> str:
    role = get_settings().db_app_user
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError("DB_APP_USER is not a safe PostgreSQL identifier")
    return role


def upgrade() -> None:
    role = _runtime_role()

    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql
        AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_current_tenant_id() TO {role}")
    op.execute(f"GRANT SELECT ON alembic_version TO {role}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}"
    )


def downgrade() -> None:
    role = _runtime_role()
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {role}"
    )
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id()")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")
