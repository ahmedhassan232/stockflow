import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_export import csv_response
from app.core.pagination import Page, PageParams
from app.core.pdf import pdf_response
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.reports.pdf import invoice_html
from app.modules.sales.schemas import (
    CancelRequest,
    PaymentIn,
    SaleCreate,
    SaleDetail,
    SaleOut,
    SaleReturnCreate,
)
from app.modules.sales.service import SaleService
from app.modules.settings.service import get_company_settings, idempotency_key, run_idempotent

router = APIRouter(prefix="/sales", tags=["Sales"])
Detail = SuccessResponse[SaleDetail]


def _service(permission: str):
    def factory(
        access: TenantAccess = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
    ) -> SaleService:
        return SaleService(db, access)

    return factory


@router.get("", response_model=SuccessResponse[Page[SaleOut]])
async def list_sales(
    page: PageParams = Depends(),
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[Literal["completed", "cancelled"] | None, Query(alias="status")] = None,
    customer_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    unpaid_only: bool = False,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    service: SaleService = Depends(_service("sales.view")),
):
    items, total = await service.search(
        page,
        q=q,
        status=status_,
        customer_id=customer_id,
        warehouse_id=warehouse_id,
        unpaid_only=unpaid_only,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(Page(items=items, total=total, page=page.page, page_size=page.page_size))


@router.post(
    "",
    response_model=Detail,
    status_code=status.HTTP_201_CREATED,
    summary="Post a sale (POS checkout)",
    description="Send an `Idempotency-Key` header: a retried checkout never creates a "
    "second invoice or a second stock movement.",
)
async def create_sale(
    data: SaleCreate,
    key: str | None = Depends(idempotency_key),
    service: SaleService = Depends(_service("sales.create")),
):
    result = await run_idempotent(
        service.db, service.access, "sales.create", key, data, lambda: service.create(data)
    )
    return ok(result, "Sale completed")


@router.get("/export", summary="Invoices as CSV (same filters as the list)")
async def export_sales(
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[Literal["completed", "cancelled"] | None, Query(alias="status")] = None,
    customer_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    unpaid_only: bool = False,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    service: SaleService = Depends(_service("sales.view")),
):
    items, _ = await service.search(
        PageParams(page=1, page_size=10_000),
        q=q,
        status=status_,
        customer_id=customer_id,
        warehouse_id=warehouse_id,
        unpaid_only=unpaid_only,
        date_from=date_from,
        date_to=date_to,
    )
    return csv_response(
        "invoices.csv",
        [
            "Number",
            "Date (UTC)",
            "Customer",
            "Warehouse",
            "Status",
            "Payment",
            "Subtotal",
            "Discount",
            "Tax",
            "Total",
            "Paid",
            "Returned",
            "Balance due",
        ],
        [
            (
                s.number,
                s.created_at,
                s.customer_name,
                s.warehouse_name,
                s.status,
                s.payment_status,
                s.subtotal,
                s.discount_amount,
                s.tax_amount,
                s.total,
                s.paid_amount,
                s.returned_amount,
                s.balance_due,
            )
            for s in items
        ],
    )


@router.get("/{sale_id}/pdf", summary="Invoice as PDF")
async def sale_pdf(
    sale_id: uuid.UUID,
    lang: Literal["ar", "en"] = "ar",
    service: SaleService = Depends(_service("sales.view")),
):
    sale = await service.detail(sale_id)
    settings = await get_company_settings(service.db, service.access.tenant_id)
    body = invoice_html(sale, service.access.tenant, settings, lang)
    return await pdf_response(f"{sale.number}.pdf", body, lang)


@router.get("/{sale_id}", response_model=Detail)
async def get_sale(sale_id: uuid.UUID, service: SaleService = Depends(_service("sales.view"))):
    return ok(await service.detail(sale_id))


@router.post("/{sale_id}/payments", response_model=Detail)
async def pay_sale(
    sale_id: uuid.UUID,
    data: PaymentIn,
    key: str | None = Depends(idempotency_key),
    service: SaleService = Depends(_service("payments.manage")),
):
    result = await run_idempotent(
        service.db,
        service.access,
        f"sales.pay:{sale_id}",
        key,
        data,
        lambda: service.pay(sale_id, data),
    )
    return ok(result, "Payment recorded")


@router.post("/{sale_id}/returns", response_model=Detail)
async def return_sale(
    sale_id: uuid.UUID,
    data: SaleReturnCreate,
    key: str | None = Depends(idempotency_key),
    service: SaleService = Depends(_service("sales.return")),
):
    result = await run_idempotent(
        service.db,
        service.access,
        f"sales.return:{sale_id}",
        key,
        data,
        lambda: service.return_items(sale_id, data),
    )
    return ok(result, "Return processed")


@router.post("/{sale_id}/cancel", response_model=Detail)
async def cancel_sale(
    sale_id: uuid.UUID,
    data: CancelRequest,
    service: SaleService = Depends(_service("sales.cancel")),
):
    return ok(await service.cancel(sale_id, data.reason), "Sale cancelled")
