"""Phase 10: let the background worker enumerate active companies.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14 21:30:00

The runtime role cannot see `tenants` without a user context (RLS). Scheduled jobs have
no user, so they call this SECURITY DEFINER function, which exposes ONLY the ids of
active companies. The job then enters each company's tenant context and does its work
under the normal RLS policies - it never gets a cross-tenant view of business data.

`tenants` uses FORCE ROW LEVEL SECURITY, which also binds the table owner, so the
function needs a SELECT policy for the owner role. That role is used only by migrations
and by this function; the runtime role gains nothing from the policy.
"""

from alembic import op

from app.core.config import get_settings

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    role = get_settings().db_app_user
    op.execute("CREATE POLICY owner_listing ON tenants FOR SELECT TO CURRENT_USER USING (true)")
    op.execute(
        """
        CREATE FUNCTION app_active_tenant_ids() RETURNS SETOF uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$ SELECT id FROM public.tenants WHERE status = 'active' ORDER BY id $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_active_tenant_ids() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_active_tenant_ids() TO {role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_active_tenant_ids()")
    op.execute("DROP POLICY IF EXISTS owner_listing ON tenants")
