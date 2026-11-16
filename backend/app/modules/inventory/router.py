import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_export import csv_response
from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.inventory.models import MOVEMENT_TYPES
from app.modules.inventory.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    BalanceOut,
    MinimumLevelSet,
    MovementOut,
    TransferCreate,
    TransferOut,
    ValuationOut,
)
from app.modules.inventory.service import InventoryService
from app.modules.settings.service import idempotency_key, run_idempotent

router = APIRouter(prefix="/inventory", tags=["Inventory"])
MovementType = Literal[MOVEMENT_TYPES]  # type: ignore[valid-type]


def _service(permission: str):
    def factory(
        access: TenantAccess = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
    ) -> InventoryService:
        return InventoryService(db, access)

    return factory


def _page(items, total, page: PageParams):
    return Page(items=items, total=total, page=page.page, page_size=page.page_size)


@router.get("", response_model=SuccessResponse[Page[BalanceOut]], summary="Stock balances")
async def list_balances(
    page: PageParams = Depends(),
    q: Annotated[str | None, Query(max_length=100)] = None,
    warehouse_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    service: InventoryService = Depends(_service("inventory.view")),
):
    items, total = await service.balances(
        page, q=q, warehouse_id=warehouse_id, product_id=product_id, low_only=False
    )
    return ok(_page(items, total, page))


@router.get("/export", summary="Stock balances as CSV")
async def export_balances(
    warehouse_id: uuid.UUID | None = None,
    low_only: bool = False,
    service: InventoryService = Depends(_service("inventory.view")),
):
    items, _ = await service.balances(
        PageParams(page=1, page_size=10_000),
        q=None,
        warehouse_id=warehouse_id,
        product_id=None,
        low_only=low_only,
    )
    show_cost = service.access.has("reports.inventory.view")  # cost data needs its own permission
    header = ["SKU", "Product", "Warehouse", "Quantity", "Minimum level", "Low"]
    if show_cost:
        header += ["Average cost", "Stock value"]
    return csv_response(
        "stock.csv",
        header,
        [
            (
                b.sku,
                b.product_name,
                b.warehouse_name,
                b.quantity,
                b.minimum_stock_level,
                "yes" if b.is_low else "",
                *((b.average_cost, b.stock_value) if show_cost else ()),
            )
            for b in items
        ],
    )


@router.get("/low-stock", response_model=SuccessResponse[Page[BalanceOut]])
async def low_stock(
    page: PageParams = Depends(),
    warehouse_id: uuid.UUID | None = None,
    service: InventoryService = Depends(_service("inventory.view")),
):
    items, total = await service.balances(
        page, q=None, warehouse_id=warehouse_id, product_id=None, low_only=True
    )
    return ok(_page(items, total, page))


@router.get("/valuation", response_model=SuccessResponse[ValuationOut])
async def valuation(service: InventoryService = Depends(_service("reports.inventory.view"))):
    return ok(await service.valuation())


@router.get("/movements", response_model=SuccessResponse[Page[MovementOut]])
async def list_movements(
    page: PageParams = Depends(),
    warehouse_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    movement_type: MovementType | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    service: InventoryService = Depends(_service("inventory.view")),
):
    items, total = await service.movements(
        page,
        warehouse_id=warehouse_id,
        product_id=product_id,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(_page([MovementOut.model_validate(m) for m in items], total, page))


@router.post(
    "/adjustments",
    response_model=SuccessResponse[AdjustmentOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_adjustment(
    data: AdjustmentCreate,
    key: str | None = Depends(idempotency_key),
    service: InventoryService = Depends(_service("inventory.adjust")),
):
    result = await run_idempotent(
        service.db, service.access, "inventory.adjust", key, data, lambda: service.adjust(data)
    )
    return ok(result, "Stock adjusted")


@router.post(
    "/transfers", response_model=SuccessResponse[TransferOut], status_code=status.HTTP_201_CREATED
)
async def create_transfer(
    data: TransferCreate,
    key: str | None = Depends(idempotency_key),
    service: InventoryService = Depends(_service("inventory.transfer")),
):
    result = await run_idempotent(
        service.db, service.access, "inventory.transfer", key, data, lambda: service.transfer(data)
    )
    return ok(result, "Stock transferred")


@router.put("/minimum-level", response_model=SuccessResponse[None])
async def set_minimum_level(
    data: MinimumLevelSet, service: InventoryService = Depends(_service("inventory.adjust"))
):
    await service.set_minimum_level(data)
    return ok(None, "Minimum stock level saved")
