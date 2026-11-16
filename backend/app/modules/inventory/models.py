import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import COST, QTY
from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, UUIDPrimaryKeyMixin

MOVEMENT_TYPES = (
    "purchase_receipt",
    "sale",
    "sale_return",
    "purchase_return",
    "adjustment_in",
    "adjustment_out",
    "transfer_in",
    "transfer_out",
)
_TYPES_SQL = ", ".join(f"'{t}'" for t in MOVEMENT_TYPES)


def _fk(cols: list[str], target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", *cols], [f"{target}.tenant_id", f"{target}.id"], ondelete="RESTRICT"
    )


class StockBalance(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Current quantity of one product in one warehouse. A cache of the ledger that is
    only ever changed together with an inventory movement, under a row lock."""

    __tablename__ = "stock_balances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "warehouse_id", "product_id"),
        _fk(["warehouse_id"], "warehouses"),
        _fk(["product_id"], "products"),
        Index("ix_stock_balances_tenant_id_product_id", "tenant_id", "product_id"),
        CheckConstraint("minimum_stock_level >= 0", name="minimum_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")
    reserved_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")
    minimum_stock_level: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InventoryMovement(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """Immutable ledger: the runtime DB role has INSERT/SELECT only on this table."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        # One business document line can produce a given movement only once.
        UniqueConstraint(
            "tenant_id",
            "reference_type",
            "reference_id",
            "line_no",
            "movement_type",
            name="uq_inventory_movements_reference",
        ),
        _fk(["warehouse_id"], "warehouses"),
        _fk(["product_id"], "products"),
        CheckConstraint(f"movement_type IN ({_TYPES_SQL})", name="type_valid"),
        CheckConstraint(
            "(quantity_in > 0 AND quantity_out = 0) OR (quantity_out > 0 AND quantity_in = 0)",
            name="exactly_one_direction",
        ),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        Index("ix_inventory_movements_product", "tenant_id", "product_id", "created_at"),
        Index("ix_inventory_movements_warehouse", "tenant_id", "warehouse_id", "created_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_in: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")
    quantity_out: Mapped[Decimal] = mapped_column(QTY, nullable=False, server_default="0")
    unit_cost: Mapped[Decimal] = mapped_column(COST, nullable=False, server_default="0")
    balance_after: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StockAdjustment(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "stock_adjustments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk(["warehouse_id"], "warehouses"),
        _fk(["product_id"], "products"),
        CheckConstraint("direction IN ('in', 'out')", name="direction_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StockTransfer(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk(["from_warehouse_id"], "warehouses"),
        _fk(["to_warehouse_id"], "warehouses"),
        CheckConstraint("from_warehouse_id <> to_warehouse_id", name="different_warehouses"),
    )

    from_warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    to_warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StockTransferItem(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    __tablename__ = "stock_transfer_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "transfer_id", "product_id"),
        ForeignKeyConstraint(
            ["tenant_id", "transfer_id"],
            ["stock_transfers.tenant_id", "stock_transfers.id"],
            ondelete="CASCADE",
        ),
        _fk(["product_id"], "products"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    transfer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
