import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

MEMBERSHIP_STATUSES = ("invited", "active", "suspended", "revoked")


class Role(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """Every role is tenant-owned. The default (system) roles are copied into each
    company at provisioning time, so composite FKs and RLS apply to them uniformly."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]*$'", name="code_format"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Membership(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """Links a global user to one company with one role."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "user_id"),
        # The role must belong to the SAME tenant as the membership.
        ForeignKeyConstraint(
            ["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'revoked')", name="status_valid"
        ),
        Index("ix_memberships_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # False: every branch of the company. True: ONLY branches listed in membership_branches
    # (an empty list then means no branch at all – explicit, fail closed).
    restricted_to_branches: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class RolePermission(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "role_id", "permission_code"),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"], ondelete="CASCADE"
        ),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    permission_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("permissions.code", ondelete="CASCADE"), nullable=False
    )


class MembershipBranch(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "membership_branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "membership_id", "branch_id"),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE"
        ),
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
