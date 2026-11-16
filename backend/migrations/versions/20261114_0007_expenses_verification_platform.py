"""Expenses, e-mail verification tokens, platform administration.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14 21:33:04.236778
"""

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("method", sa.String(length=20), server_default="cash", nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'voided')", name=op.f("ck_expenses_status_valid")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_expenses_amount_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_expenses_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name=op.f("fk_expenses_tenant_id_branch_id_branches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_expenses_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expenses")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_expenses_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "number", name=op.f("uq_expenses_tenant_id_number")),
    )
    op.create_index(
        "ix_expenses_tenant_id_expense_date",
        "expenses",
        ["tenant_id", "expense_date"],
        unique=False,
    )
    op.add_column(
        "password_reset_tokens",
        sa.Column("purpose", sa.String(length=20), server_default="password_reset", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    for table in ("expenses",):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    for table in ("expenses",):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = app_current_tenant_id()) "
            f"WITH CHECK (tenant_id = app_current_tenant_id())"
        )

    # ── platform administration ──
    # FORCE RLS binds the table owner too, so the SECURITY DEFINER functions below need
    # owner-only policies. The runtime role gains nothing from them: it can reach this
    # data only through the functions, and each function re-checks inside the database
    # that the current user (app.user_id) is a platform administrator.
    op.execute(
        "CREATE POLICY owner_update ON tenants FOR UPDATE TO CURRENT_USER USING (true) WITH CHECK (true)"
    )
    for table in ("memberships", "roles"):
        op.execute(
            f"CREATE POLICY owner_listing ON {table} FOR SELECT TO CURRENT_USER USING (true)"
        )
    op.execute(
        """
        CREATE FUNCTION app_is_platform_admin() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.users u
                WHERE u.id = public.app_current_user_id() AND u.is_platform_admin AND u.is_active
            )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION platform_list_tenants()
        RETURNS TABLE (id uuid, name text, slug text, status text, currency text,
                       created_at timestamptz, member_count bigint,
                       owner_name text, owner_email text)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'platform administrator required';
            END IF;
            RETURN QUERY
            SELECT t.id, t.name::text, t.slug::text, t.status::text, t.currency::text, t.created_at,
                   (SELECT count(*) FROM public.memberships m WHERE m.tenant_id = t.id),
                   o.full_name::text, o.email::text
            FROM public.tenants t
            LEFT JOIN LATERAL (
                SELECT u.full_name, u.email
                FROM public.memberships m
                JOIN public.roles r ON r.tenant_id = m.tenant_id AND r.id = m.role_id
                JOIN public.users u ON u.id = m.user_id
                WHERE m.tenant_id = t.id AND r.code = 'owner'
                ORDER BY m.joined_at LIMIT 1
            ) o ON true
            ORDER BY t.created_at DESC;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION platform_set_tenant_status(p_tenant uuid, p_status text) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'platform administrator required';
            END IF;
            UPDATE public.tenants SET status = p_status WHERE id = p_tenant;
            RETURN FOUND;
        END
        $$
        """
    )
    role = get_settings().db_app_user
    # The application role can never grant platform administration, not even through a
    # bug or SQL injection: only the owner role (CLI) may set the flag.
    op.execute(
        f"""
        CREATE FUNCTION guard_platform_admin_flag() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_user = '{role}' AND NEW.is_platform_admin
               AND (TG_OP = 'INSERT' OR NOT OLD.is_platform_admin) THEN
                RAISE EXCEPTION USING ERRCODE = '42501',
                    MESSAGE = 'is_platform_admin can only be granted by the platform CLI';
            END IF;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_users_guard_platform_admin BEFORE INSERT OR UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION guard_platform_admin_flag()"
    )
    for fn in (
        "app_is_platform_admin()",
        "platform_list_tenants()",
        "platform_set_tenant_status(uuid, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {role}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_guard_platform_admin ON users")
    op.execute("DROP FUNCTION IF EXISTS guard_platform_admin_flag()")
    for fn in (
        "platform_set_tenant_status(uuid, text)",
        "platform_list_tenants()",
        "app_is_platform_admin()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute("DROP POLICY IF EXISTS owner_update ON tenants")
    for table in ("memberships", "roles"):
        op.execute(f"DROP POLICY IF EXISTS owner_listing ON {table}")
    op.drop_column("users", "is_platform_admin")
    op.drop_column("password_reset_tokens", "purpose")
    op.drop_index("ix_expenses_tenant_id_expense_date", table_name="expenses")
    op.drop_table("expenses")
