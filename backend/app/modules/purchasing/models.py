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

PO_STATUSES = ("draft", "ordered", "partially_received", "received", "cancelled")


class PurchaseOrder(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        tenant_fk(["supplier_id"], "suppliers"),
        tenant_fk(["warehouse_id"], "warehouses"),
        CheckConstraint(
            "status IN ('draft','ordered','partially_received','received','cancelled')",
            name="status_valid",
        ),
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total >= 0", name="amounts_valid"),
        CheckConstraint("paid_amount >= 0 AND paid_amount <= total", name="paid_within_total"),
        Index("ix_purchase_orders_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_purchase_orders_tenant_id_supplier_id", "tenant_id", "supplier_id"),
    )

    number: Mapped[str] = mapped_column(String(30), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = created_by_column()


class PurchaseOrderItem(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "purchase_order_id", "line_no"),
        UniqueConstraint("tenant_id", "purchase_order_id", "product_id"),
        tenant_fk(["purchase_order_id"], "purchase_orders"),
        tenant_fk(["product_id"], "products"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity",
            name="received_within_ordered",
        ),
        CheckConstraint(
            "returned_quantity >= 0 AND returned_quantity <= received_quantity",
            name="returned_within_received",
        ),
    )

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(COST, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")
    returned_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")


class PurchaseReceipt(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Goods received note. Append-only."""

    __tablename__ = "purchase_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        tenant_fk(["purchase_order_id"], "purchase_orders"),
        tenant_fk(["warehouse_id"], "warehouses"),
        CheckConstraint("kind IN ('receipt','return')", name="kind_valid"),
    )

    number: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="receipt")
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = created_by_column()
    created_at: Mapped[datetime] = created_at_column()


class PurchaseReceiptItem(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "purchase_receipt_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "purchase_receipt_id", "line_no"),
        tenant_fk(["purchase_receipt_id"], "purchase_receipts"),
        tenant_fk(["purchase_order_item_id"], "purchase_order_items"),
        tenant_fk(["product_id"], "products"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    purchase_receipt_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_order_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(COST, nullable=False)
