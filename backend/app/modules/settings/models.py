import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import RATE
from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CompanySettings(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """One row per company (created at provisioning)."""

    __tablename__ = "company_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),
        CheckConstraint("default_tax_rate >= 0 AND default_tax_rate <= 100", name="tax_rate_range"),
    )

    tax_number: Mapped[str | None] = mapped_column(String(50))
    default_tax_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, server_default="0")
    # Default: selling more than the available stock is refused.
    allow_negative_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    invoice_footer: Mapped[str | None] = mapped_column(Text)


class DocumentSequence(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Per-company document numbering. The row is locked FOR UPDATE while a number is
    taken, so concurrent postings can never receive the same number."""

    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "doc_type"),
        CheckConstraint("next_number > 0", name="next_number_positive"),
    )

    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class IdempotencyKey(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "operation", "key"),
    )

    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
