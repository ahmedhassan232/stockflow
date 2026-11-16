"""Platform audit log: every company suspension / re-activation is recorded.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14 23:00:00

The row is written INSIDE `platform_set_tenant_status()` (SECURITY DEFINER), in the same
transaction as the status change, so an action cannot happen without its log entry. The
application role has no privilege on the table at all: it can neither forge nor erase
entries, and reads go through `platform_audit_entries()`, which re-checks the caller.
"""

from alembic import op

from app.core.config import get_settings

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_DENIED = "RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'platform administrator required'"


def upgrade() -> None:
    role = get_settings().db_app_user
    op.execute(
        """
        CREATE TABLE platform_audit_logs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            action varchar(40) NOT NULL,
            target_company_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            target_company_name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_platform_audit_logs_created_at ON platform_audit_logs (created_at)")
    op.execute(f"REVOKE ALL ON platform_audit_logs FROM {role}")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION platform_set_tenant_status(p_tenant uuid, p_status text)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_name text;
            v_old text;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                {_DENIED};
            END IF;
            SELECT name, status INTO v_name, v_old FROM public.tenants
            WHERE id = p_tenant FOR UPDATE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
            IF v_old IS DISTINCT FROM p_status THEN
                UPDATE public.tenants SET status = p_status WHERE id = p_tenant;
                INSERT INTO public.platform_audit_logs
                    (actor_user_id, action, target_company_id, target_company_name)
                VALUES (public.app_current_user_id(),
                        CASE p_status WHEN 'suspended' THEN 'company.suspended'
                                      ELSE 'company.activated' END,
                        p_tenant, v_name);
            END IF;
            RETURN true;
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION platform_audit_entries(p_limit integer DEFAULT 100)
        RETURNS TABLE (id uuid, action text, company_name text, actor_name text,
                       actor_email text, created_at timestamptz)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                {_DENIED};
            END IF;
            RETURN QUERY
            SELECT l.id, l.action::text, l.target_company_name, u.full_name::text,
                   u.email::text, l.created_at
            FROM public.platform_audit_logs l
            JOIN public.users u ON u.id = l.actor_user_id
            ORDER BY l.created_at DESC
            LIMIT least(greatest(p_limit, 1), 500);
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION platform_audit_entries(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION platform_audit_entries(integer) TO {role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS platform_audit_entries(integer)")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION platform_set_tenant_status(p_tenant uuid, p_status text)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                {_DENIED};
            END IF;
            UPDATE public.tenants SET status = p_status WHERE id = p_tenant;
            RETURN FOUND;
        END
        $$
        """
    )
    op.execute("DROP TABLE IF EXISTS platform_audit_logs")
