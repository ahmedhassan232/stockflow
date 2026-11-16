import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, UUIDPrimaryKeyMixin, created_at_column


class Notification(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Company-wide in-app notification (e.g. low stock). `dedupe_key` keeps one open
    notification per subject; it is cleared when the notification is read."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "dedupe_key"),
        Index("ix_notifications_tenant_id_created_at", "tenant_id", "created_at"),
    )

    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSONB)
    required_permission: Mapped[str | None] = mapped_column(String(60))
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()


class AuditLog(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Who did what. Append-only for the application role."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    summary: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
