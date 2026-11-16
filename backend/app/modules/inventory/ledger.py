"""The ONLY code path that changes stock. Used by adjustments, transfers, purchase
receipts, sales and returns.

Rules enforced here:
* a balance is changed only together with an immutable movement row;
* the balance row is locked (SELECT … FOR UPDATE) before it is read, so two concurrent
  operations can never both spend the same stock;
* rows are locked in a deterministic order (products by id, then balances by
  warehouse/product) so multi-line documents cannot deadlock each other;
* stock may not go negative unless the company setting explicitly allows it.
"""

import uuid
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.money import ZERO, cost
from app.modules.catalog.models import Product
from app.modules.inventory.models import InventoryMovement, StockBalance

INBOUND = {"purchase_receipt", "sale_return", "adjustment_in", "transfer_in"}
BalanceKey = tuple[uuid.UUID, uuid.UUID]  # (warehouse_id, product_id)


class InsufficientStockError(AppError):
    status_code = 409
    code = "INSUFFICIENT_STOCK"
    message = "Not enough stock available"


class StockLedger:
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        allow_negative: bool = False,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.allow_negative = allow_negative

    async def lock_products(self, product_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Product]:
        ids = sorted(set(product_ids))
        rows = await self.db.execute(
            select(Product)
            .where(Product.tenant_id == self.tenant_id, Product.id.in_(ids))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {p.id: p for p in rows.scalars().all()}

    async def lock_balances(self, keys: Iterable[BalanceKey]) -> dict[BalanceKey, StockBalance]:
        ordered = sorted(set(keys))
        if not ordered:
            return {}
        await self.db.execute(
            pg_insert(StockBalance)
            .values(
                [
                    {"tenant_id": self.tenant_id, "warehouse_id": w, "product_id": p}
                    for w, p in ordered
                ]
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "warehouse_id", "product_id"])
        )
        rows = await self.db.execute(
            select(StockBalance)
            .where(
                StockBalance.tenant_id == self.tenant_id,
                tuple_(StockBalance.warehouse_id, StockBalance.product_id).in_(ordered),
            )
            .order_by(StockBalance.warehouse_id, StockBalance.product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {(b.warehouse_id, b.product_id): b for b in rows.scalars().all()}

    async def move(
        self,
        balance: StockBalance,
        *,
        movement_type: str,
        quantity: Decimal,
        unit_cost: Decimal,
        reference_type: str,
        reference_id: uuid.UUID,
        line_no: int = 0,
        reason: str | None = None,
    ) -> InventoryMovement:
        """`balance` must come from lock_balances() in the current transaction."""
        if quantity <= ZERO:
            raise AppError("Quantity must be greater than zero")
        inbound = movement_type in INBOUND
        new_quantity = balance.quantity + quantity if inbound else balance.quantity - quantity
        if not inbound and new_quantity < ZERO and not self.allow_negative:
            raise InsufficientStockError(
                details={
                    "product_id": str(balance.product_id),
                    "warehouse_id": str(balance.warehouse_id),
                    "available": str(balance.quantity),
                    "requested": str(quantity),
                }
            )
        balance.quantity = new_quantity
        movement = InventoryMovement(
            tenant_id=self.tenant_id,
            product_id=balance.product_id,
            warehouse_id=balance.warehouse_id,
            movement_type=movement_type,
            quantity_in=quantity if inbound else ZERO,
            quantity_out=ZERO if inbound else quantity,
            unit_cost=cost(unit_cost),
            balance_after=new_quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            line_no=line_no,
            reason=reason,
            created_by=self.user_id,
        )
        self.db.add(movement)
        await self.db.flush()
        return movement

    async def total_on_hand(self, product_id: uuid.UUID) -> Decimal:
        total = await self.db.execute(
            select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
                StockBalance.tenant_id == self.tenant_id, StockBalance.product_id == product_id
            )
        )
        return Decimal(total.scalar_one())

    async def apply_receipt_cost(
        self, product: Product, received_quantity: Decimal, unit_cost: Decimal
    ) -> Decimal:
        """Weighted average cost. Call BEFORE the inbound movement is applied, with the
        product row locked:

            new_avg = (on_hand × old_avg + received × unit_cost) / (on_hand + received)

        `on_hand` is the company-wide quantity, floored at zero (if stock was oversold the
        negative part carries no cost)."""
        on_hand = max(await self.total_on_hand(product.id), ZERO)
        total = on_hand + received_quantity
        if total > ZERO:
            product.average_cost = cost(
                (on_hand * product.average_cost + received_quantity * unit_cost) / total
            )
        return product.average_cost
