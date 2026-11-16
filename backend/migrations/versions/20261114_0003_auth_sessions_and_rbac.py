"""Authentication sessions and role-based access control.

* auth_sessions / refresh_tokens / password_reset_tokens – global identity tables. Only
  SHA-256 hashes of opaque tokens are stored.
* permissions – global read-only catalogue (runtime role: SELECT only), seeded here.
* role_permissions / membership_branches – tenant-owned, forced RLS, composite FKs.
* memberships.restricted_to_branches – explicit branch restriction flag.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 20:19:31.576959
"""

import re

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW_TENANT_TABLES = ("role_permissions", "membership_branches")

# Frozen copy: migrations must not import the live catalogue.
PERMISSIONS = {
    "settings.view": "View company settings",
    "settings.update": "Update company settings",
    "branches.view": "View branches",
    "branches.manage": "Create and update branches",
    "warehouses.view": "View warehouses",
    "warehouses.manage": "Create and update warehouses",
    "employees.view": "View employees",
    "employees.manage": "Invite, update and remove employees",
    "roles.manage": "Manage roles and their permissions",
    "products.view": "View products",
    "products.create": "Create products",
    "products.update": "Update products",
    "products.delete": "Deactivate products",
    "categories.manage": "Manage categories and units",
    "inventory.view": "View stock and movements",
    "inventory.adjust": "Adjust stock",
    "inventory.transfer": "Transfer stock between warehouses",
    "suppliers.view": "View suppliers",
    "suppliers.manage": "Manage suppliers",
    "purchases.view": "View purchases",
    "purchases.create": "Create purchases",
    "purchases.receive": "Receive goods",
    "purchases.cancel": "Cancel purchases",
    "customers.view": "View customers",
    "customers.manage": "Manage customers",
    "sales.view": "View sales",
    "sales.create": "Create and post sales",
    "sales.cancel": "Cancel sales",
    "sales.return": "Process sales returns",
    "payments.view": "View payments",
    "payments.manage": "Record payments",
    "expenses.view": "View expenses",
    "expenses.manage": "Manage expenses",
    "reports.sales.view": "View sales reports",
    "reports.inventory.view": "View inventory reports",
    "reports.financial.view": "View financial reports",
}


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_permissions")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("active_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=50), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["active_tenant_id"],
            ["tenants.id"],
            name=op.f("fk_auth_sessions_active_tenant_id_tenants"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "password_reset_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name=op.f("fk_refresh_tokens_session_id_auth_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"], unique=False)
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.String(length=60), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name=op.f("fk_role_permissions_permission_code_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name=op.f("fk_role_permissions_tenant_id_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_role_permissions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_role_permissions_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_code",
            name=op.f("uq_role_permissions_tenant_id_role_id_permission_code"),
        ),
    )
    op.create_table(
        "membership_branches",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name=op.f("fk_membership_branches_tenant_id_branch_id_branches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            name=op.f("fk_membership_branches_tenant_id_membership_id_memberships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_membership_branches_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_branches")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_membership_branches_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "membership_id",
            "branch_id",
            name=op.f("uq_membership_branches_tenant_id_membership_id_branch_id"),
        ),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "restricted_to_branches", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    perms = sa.table("permissions", sa.column("code"), sa.column("description"))
    op.bulk_insert(perms, [{"code": c, "description": d} for c, d in PERMISSIONS.items()])
    role = get_settings().db_app_user
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError("DB_APP_USER is not a safe PostgreSQL identifier")
    op.execute(f"REVOKE INSERT, UPDATE, DELETE ON permissions FROM {role}")

    for table in NEW_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = app_current_tenant_id()) "
            f"WITH CHECK (tenant_id = app_current_tenant_id())"
        )


def downgrade() -> None:
    op.drop_column("memberships", "restricted_to_branches")
    op.drop_table("membership_branches")
    op.drop_table("role_permissions")
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("permissions")
