from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class _Party(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin):
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(CITEXT)
    address: Mapped[str | None] = mapped_column(Text)
    tax_number: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Supplier(_Party, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_suppliers_tenant_id_name", "tenant_id", "name"),
    )


class Customer(_Party, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_customers_tenant_id_name", "tenant_id", "name"),
        Index("ix_customers_tenant_id_phone", "tenant_id", "phone"),
    )
