"""Reusable column sets. Every tenant-owned model MUST inherit TenantOwnedMixin."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Maintained by the `set_updated_at` trigger attached in the migration.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TenantOwnedMixin:
    """Adds `tenant_id`. The migration for the table must also:
    * add UNIQUE (tenant_id, id) so other tables can reference it with a composite FK,
    * ENABLE + FORCE row level security with the `tenant_isolation` policy.
    `tests/test_schema_guards.py` fails the build if either is forgotten.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)


def tenant_fk(cols: list[str], target: str) -> ForeignKeyConstraint:
    """Composite FK (tenant_id, col) -> target(tenant_id, id): a row can never point at
    another company's row."""
    return ForeignKeyConstraint(
        ["tenant_id", *cols], [f"{target}.tenant_id", f"{target}.id"], ondelete="RESTRICT"
    )


def created_by_column() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
