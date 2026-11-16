from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

TENANT_STATUSES = ("active", "suspended")


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A company. The row's own `id` is its tenant id (RLS: id = current tenant)."""

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="status_valid"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso4217"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EGP")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Africa/Cairo")
