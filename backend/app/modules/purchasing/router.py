import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.purchasing.models import PO_STATUSES
from app.modules.purchasing.schemas import (
    PaymentIn,
    PurchaseCreate,
    PurchaseDetail,
    PurchaseOut,
    PurchaseReturnRequest,
    ReceiveRequest,
)
from app.modules.purchasing.service import PurchaseService
from app.modules.settings.service import idempotency_key, run_idempotent

router = APIRouter(prefix="/purchases", tags=["Purchasing"])
Detail = SuccessResponse[PurchaseDetail]


def _service(permission: str):
    def factory(
        access: TenantAccess = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
    ) -> PurchaseService:
        return PurchaseService(db, access)

    return factory


@router.get("", response_model=SuccessResponse[Page[PurchaseOut]])
async def list_purchases(
    page: PageParams = Depends(),
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[Literal[PO_STATUSES] | None, Query(alias="status")] = None,  # type: ignore[valid-type]
    supplier_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    service: PurchaseService = Depends(_service("purchases.view")),
):
    items, total = await service.search(
        page, q=q, status=status_, supplier_id=supplier_id, date_from=date_from, date_to=date_to
    )
    return ok(Page(items=items, total=total, page=page.page, page_size=page.page_size))


@router.post("", response_model=Detail, status_code=status.HTTP_201_CREATED)
async def create_purchase(
    data: PurchaseCreate,
    key: str | None = Depends(idempotency_key),
    service: PurchaseService = Depends(_service("purchases.create")),
):
    result = await run_idempotent(
        service.db, service.access, "purchases.create", key, data, lambda: service.create(data)
    )
    return ok(result, "Purchase order created")


@router.get("/{purchase_id}", response_model=Detail)
async def get_purchase(
    purchase_id: uuid.UUID, service: PurchaseService = Depends(_service("purchases.view"))
):
    return ok(await service.detail(purchase_id))


@router.post("/{purchase_id}/confirm", response_model=Detail)
async def confirm_purchase(
    purchase_id: uuid.UUID, service: PurchaseService = Depends(_service("purchases.create"))
):
    return ok(await service.confirm(purchase_id), "Purchase order confirmed")


@router.post("/{purchase_id}/cancel", response_model=Detail)
async def cancel_purchase(
    purchase_id: uuid.UUID, service: PurchaseService = Depends(_service("purchases.cancel"))
):
    return ok(await service.cancel(purchase_id), "Purchase order cancelled")


@router.post("/{purchase_id}/receive", response_model=Detail)
async def receive_purchase(
    purchase_id: uuid.UUID,
    data: ReceiveRequest,
    key: str | None = Depends(idempotency_key),
    service: PurchaseService = Depends(_service("purchases.receive")),
):
    result = await run_idempotent(
        service.db,
        service.access,
        f"purchases.receive:{purchase_id}",
        key,
        data,
        lambda: service.receive(purchase_id, data),
    )
    return ok(result, "Goods received")


@router.post("/{purchase_id}/returns", response_model=Detail)
async def return_purchase(
    purchase_id: uuid.UUID,
    data: PurchaseReturnRequest,
    key: str | None = Depends(idempotency_key),
    service: PurchaseService = Depends(_service("purchases.cancel")),
):
    result = await run_idempotent(
        service.db,
        service.access,
        f"purchases.return:{purchase_id}",
        key,
        data,
        lambda: service.return_goods(purchase_id, data),
    )
    return ok(result, "Goods returned to supplier")


@router.post("/{purchase_id}/payments", response_model=Detail)
async def pay_purchase(
    purchase_id: uuid.UUID,
    data: PaymentIn,
    key: str | None = Depends(idempotency_key),
    service: PurchaseService = Depends(_service("payments.manage")),
):
    result = await run_idempotent(
        service.db,
        service.access,
        f"purchases.pay:{purchase_id}",
        key,
        data,
        lambda: service.pay(purchase_id, data),
    )
    return ok(result, "Payment recorded")
