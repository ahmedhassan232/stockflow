import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import ensure_exists
from app.core.exceptions import AppError, NotFoundError
from app.core.money import ZERO, money
from app.core.pagination import PageParams
from app.db.repository import like_pattern
from app.modules.authorization.service import TenantAccess
from app.modules.catalog.models import Product
from app.modules.inventory.ledger import StockLedger
from app.modules.inventory.models import (
    InventoryMovement,
    StockAdjustment,
    StockBalance,
    StockTransfer,
    StockTransferItem,
)
from app.modules.inventory.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    BalanceOut,
    MinimumLevelSet,
    TransferCreate,
    TransferItemOut,
    TransferOut,
    ValuationOut,
    WarehouseValuation,
)
from app.modules.organization.models import Warehouse
from app.modules.settings.service import get_company_settings


async def get_accessible_warehouse(
    db: AsyncSession, access: TenantAccess, warehouse_id: uuid.UUID, *, must_be_active: bool = True
) -> Warehouse:
    """A warehouse outside the caller's company OR branch scope is 'not found'."""
    warehouse = (
        await db.execute(
            select(Warehouse).where(
                Warehouse.tenant_id == access.tenant_id, Warehouse.id == warehouse_id
            )
        )
    ).scalar_one_or_none()
    if warehouse is None or not access.can_access_branch(warehouse.branch_id):
        raise NotFoundError("Warehouse not found")
    if must_be_active and not warehouse.is_active:
        raise AppError("Warehouse is inactive", code="INACTIVE_REFERENCE")
    return warehouse


def warehouse_scope(access: TenantAccess) -> list[ColumnElement[bool]]:
    if not access.restricted_to_branches:
        return []
    return [Warehouse.branch_id.in_(access.branch_ids)]


class InventoryService:
    def __init__(self, db: AsyncSession, access: TenantAccess) -> None:
        self.db = db
        self.access = access
        self.tenant_id = access.tenant_id

    async def _ledger(self) -> StockLedger:
        settings = await get_company_settings(self.db, self.tenant_id)
        return StockLedger(
            self.db,
            self.tenant_id,
            self.access.user_id,
            allow_negative=settings.allow_negative_stock,
        )

    async def _tracked_product(self, product_id: uuid.UUID) -> Product:
        product = await ensure_exists(self.db, self.tenant_id, Product, product_id, "Product")
        if not product.track_inventory:
            raise AppError("This product does not track inventory", code="NOT_TRACKED")
        return product

    # ── writes ──

    async def adjust(self, data: AdjustmentCreate) -> AdjustmentOut:
        await get_accessible_warehouse(self.db, self.access, data.warehouse_id)
        await self._tracked_product(data.product_id)
        ledger = await self._ledger()
        product = (await ledger.lock_products([data.product_id]))[data.product_id]
        key = (data.warehouse_id, data.product_id)
        balance = (await ledger.lock_balances([key]))[key]

        adjustment = StockAdjustment(
            tenant_id=self.tenant_id,
            created_by=self.access.user_id,
            **data.model_dump(),
        )
        self.db.add(adjustment)
        await self.db.flush()
        movement = await ledger.move(
            balance,
            movement_type=f"adjustment_{data.direction}",
            quantity=data.quantity,
            unit_cost=product.average_cost,  # valued at current average; average unchanged
            reference_type="stock_adjustment",
            reference_id=adjustment.id,
            reason=data.reason,
        )
        await self.db.refresh(adjustment)
        out = AdjustmentOut.model_validate(adjustment)
        out.balance_after = movement.balance_after
        return out

    async def transfer(self, data: TransferCreate) -> TransferOut:
        """Atomic: every transfer-out and transfer-in happens, or none does."""
        await get_accessible_warehouse(self.db, self.access, data.from_warehouse_id)
        await get_accessible_warehouse(self.db, self.access, data.to_warehouse_id)
        for item in data.items:
            await self._tracked_product(item.product_id)

        ledger = await self._ledger()
        products = await ledger.lock_products(i.product_id for i in data.items)
        balances = await ledger.lock_balances(
            (w, i.product_id)
            for i in data.items
            for w in (data.from_warehouse_id, data.to_warehouse_id)
        )
        transfer = StockTransfer(
            tenant_id=self.tenant_id,
            from_warehouse_id=data.from_warehouse_id,
            to_warehouse_id=data.to_warehouse_id,
            notes=data.notes,
            created_by=self.access.user_id,
        )
        self.db.add(transfer)
        await self.db.flush()
        for line_no, item in enumerate(data.items, start=1):
            self.db.add(
                StockTransferItem(
                    tenant_id=self.tenant_id,
                    transfer_id=transfer.id,
                    product_id=item.product_id,
                    line_no=line_no,
                    quantity=item.quantity,
                )
            )
            common = {
                "quantity": item.quantity,
                "unit_cost": products[item.product_id].average_cost,
                "reference_type": "stock_transfer",
                "reference_id": transfer.id,
                "line_no": line_no,
            }
            # Out first: an insufficient source aborts the whole transaction.
            await ledger.move(
                balances[(data.from_warehouse_id, item.product_id)],
                movement_type="transfer_out",
                **common,
            )
            await ledger.move(
                balances[(data.to_warehouse_id, item.product_id)],
                movement_type="transfer_in",
                **common,
            )
        await self.db.refresh(transfer)
        return TransferOut(
            id=transfer.id,
            from_warehouse_id=transfer.from_warehouse_id,
            to_warehouse_id=transfer.to_warehouse_id,
            notes=transfer.notes,
            created_by=transfer.created_by,
            created_at=transfer.created_at,
            items=[
                TransferItemOut(product_id=i.product_id, quantity=i.quantity) for i in data.items
            ],
        )

    async def set_minimum_level(self, data: MinimumLevelSet) -> None:
        await get_accessible_warehouse(
            self.db, self.access, data.warehouse_id, must_be_active=False
        )
        await self._tracked_product(data.product_id)
        ledger = await self._ledger()
        key = (data.warehouse_id, data.product_id)
        balance = (await ledger.lock_balances([key]))[key]
        balance.minimum_stock_level = data.minimum_stock_level
        await self.db.flush()

    # ── reads ──

    def _balance_query(self):
        return (
            select(StockBalance, Product, Warehouse.name)
            .join(
                Product,
                (Product.tenant_id == StockBalance.tenant_id)
                & (Product.id == StockBalance.product_id),
            )
            .join(
                Warehouse,
                (Warehouse.tenant_id == StockBalance.tenant_id)
                & (Warehouse.id == StockBalance.warehouse_id),
            )
            .where(StockBalance.tenant_id == self.tenant_id, *warehouse_scope(self.access))
        )

    async def balances(
        self,
        page: PageParams,
        *,
        q: str | None,
        warehouse_id: uuid.UUID | None,
        product_id: uuid.UUID | None,
        low_only: bool,
    ) -> tuple[list[BalanceOut], int]:
        stmt = self._balance_query()
        if q:
            p = like_pattern(q)
            stmt = stmt.where(
                or_(Product.name.ilike(p), Product.sku.ilike(p), Product.barcode.ilike(p))
            )
        if warehouse_id:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
        if product_id:
            stmt = stmt.where(StockBalance.product_id == product_id)
        if low_only:
            stmt = stmt.where(
                Product.is_active.is_(True),
                StockBalance.minimum_stock_level > 0,
                StockBalance.quantity <= StockBalance.minimum_stock_level,
            )
        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = await self.db.execute(
            stmt.order_by(Product.name, Warehouse.name, StockBalance.id)
            .limit(page.page_size)
            .offset(page.offset)
        )
        items = [
            BalanceOut(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                warehouse_id=balance.warehouse_id,
                warehouse_name=warehouse_name,
                quantity=balance.quantity,
                minimum_stock_level=balance.minimum_stock_level,
                is_low=balance.minimum_stock_level > ZERO
                and balance.quantity <= balance.minimum_stock_level,
                average_cost=product.average_cost,
                stock_value=money(max(balance.quantity, ZERO) * product.average_cost),
            )
            for balance, product, warehouse_name in rows.all()
        ]
        return items, total

    async def movements(
        self,
        page: PageParams,
        *,
        warehouse_id: uuid.UUID | None,
        product_id: uuid.UUID | None,
        movement_type: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[InventoryMovement], int]:
        stmt = (
            select(InventoryMovement)
            .join(
                Warehouse,
                (Warehouse.tenant_id == InventoryMovement.tenant_id)
                & (Warehouse.id == InventoryMovement.warehouse_id),
            )
            .where(InventoryMovement.tenant_id == self.tenant_id, *warehouse_scope(self.access))
        )
        for column, value in (
            (InventoryMovement.warehouse_id, warehouse_id),
            (InventoryMovement.product_id, product_id),
            (InventoryMovement.movement_type, movement_type),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        if date_from:
            stmt = stmt.where(InventoryMovement.created_at >= date_from)
        if date_to:
            stmt = stmt.where(InventoryMovement.created_at < date_to)
        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = await self.db.execute(
            stmt.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id)
            .limit(page.page_size)
            .offset(page.offset)
        )
        return list(rows.scalars().all()), total

    async def valuation(self) -> ValuationOut:
        positive = func.greatest(StockBalance.quantity, 0)
        rows = await self.db.execute(
            select(
                Warehouse.id,
                Warehouse.name,
                func.coalesce(func.sum(positive), 0),
                func.coalesce(func.sum(positive * Product.average_cost), 0),
            )
            .select_from(Warehouse)
            .outerjoin(
                StockBalance,
                (StockBalance.tenant_id == Warehouse.tenant_id)
                & (StockBalance.warehouse_id == Warehouse.id),
            )
            .outerjoin(
                Product,
                (Product.tenant_id == StockBalance.tenant_id)
                & (Product.id == StockBalance.product_id),
            )
            .where(Warehouse.tenant_id == self.tenant_id, *warehouse_scope(self.access))
            .group_by(Warehouse.id, Warehouse.name)
            .order_by(Warehouse.name)
        )
        warehouses = [
            WarehouseValuation(
                warehouse_id=wid,
                warehouse_name=name,
                total_quantity=quantity,
                stock_value=money(value),
            )
            for wid, name, quantity, value in rows.all()
        ]
        return ValuationOut(
            total_value=money(sum((w.stock_value for w in warehouses), ZERO)), warehouses=warehouses
        )
