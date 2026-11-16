import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import COST, MONEY, QTY, RATE
from app.db.base import Base
from app.db.mixins import (
    TenantOwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    created_at_column,
    created_by_column,
    tenant_fk,
)

PAYMENT_METHODS = ("cash", "card", "bank_transfer", "wallet")


class Sale(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """A posted sales invoice. Amounts are computed by the backend and never edited;
    corrections are made with returns or cancellation."""

    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        tenant_fk(["customer_id"], "customers"),
        tenant_fk(["warehouse_id"], "warehouses"),
        CheckConstraint("status IN ('completed','cancelled')", name="status_valid"),
        CheckConstraint(
            "subtotal >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND total >= 0",
            name="amounts_valid",
        ),
        CheckConstraint("paid_amount >= 0 AND paid_amount <= total", name="paid_within_total"),
        CheckConstraint("returned_amount >= 0 AND returned_amount <= total", name="returned_valid"),
        Index("ix_sales_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_sales_tenant_id_customer_id", "tenant_id", "customer_id"),
    )

    number: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="completed")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cost_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    returned_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = created_by_column()


class SaleItem(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "sale_id", "line_no"),
        tenant_fk(["sale_id"], "sales"),
        tenant_fk(["product_id"], "products"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND discount_amount >= 0", name="price_valid"),
        CheckConstraint("unit_cost_at_sale >= 0", name="cost_non_negative"),
        CheckConstraint(
            "returned_quantity >= 0 AND returned_quantity <= quantity", name="returned_within_sold"
        ),
        Index("ix_sale_items_tenant_id_product_id", "tenant_id", "product_id"),
    )

    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)  # snapshot
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    tax_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Average cost at the moment of sale: profit reports never change retroactively.
    unit_cost_at_sale: Mapped[Decimal] = mapped_column(COST, nullable=False)
    returned_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")


class SaleReturn(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Append-only."""

    __tablename__ = "sale_returns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        tenant_fk(["sale_id"], "sales"),
        CheckConstraint("total >= 0 AND refund_amount >= 0", name="amounts_valid"),
        Index("ix_sale_returns_tenant_id_created_at", "tenant_id", "created_at"),
    )

    number: Mapped[str] = mapped_column(String(30), nullable=False)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cost_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    refund_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = created_by_column()
    created_at: Mapped[datetime] = created_at_column()


class SaleReturnItem(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "sale_return_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "sale_return_id", "line_no"),
        tenant_fk(["sale_return_id"], "sale_returns"),
        tenant_fk(["sale_item_id"], "sale_items"),
        tenant_fk(["product_id"], "products"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    sale_return_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class Payment(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Money movement, append-only. direction 'in' = received from a customer (or a
    supplier refund), 'out' = paid to a supplier (or a customer refund)."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        tenant_fk(["sale_id"], "sales"),
        tenant_fk(["purchase_order_id"], "purchase_orders"),
        CheckConstraint("direction IN ('in','out')", name="direction_valid"),
        CheckConstraint("method IN ('cash','card','bank_transfer','wallet')", name="method_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(sale_id IS NOT NULL) <> (purchase_order_id IS NOT NULL)", name="exactly_one_document"
        ),
        Index("ix_payments_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_payments_tenant_id_sale_id", "tenant_id", "sale_id"),
    )

    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reference: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID] = created_by_column()
    created_at: Mapped[datetime] = created_at_column()
