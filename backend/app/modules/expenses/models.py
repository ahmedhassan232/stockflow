import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import MONEY
from app.db.base import Base
from app.db.mixins import (
    TenantOwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    created_by_column,
    tenant_fk,
)


class Expense(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """An operating expense (rent, salaries, utilities ...). Amount, date and category
    are fixed once recorded; a mistake is corrected by voiding (with a reason) and
    recording a new expense, so the history stays auditable."""

    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        tenant_fk(["branch_id"], "branches"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('active', 'voided')", name="status_valid"),
        Index("ix_expenses_tenant_id_expense_date", "tenant_id", "expense_date"),
    )

    number: Mapped[str] = mapped_column(String(30), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, server_default="cash")
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = created_by_column()
