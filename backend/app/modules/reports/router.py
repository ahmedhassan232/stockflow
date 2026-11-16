import uuid
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_export import csv_response
from app.core.pdf import pdf_response
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import get_tenant_access, require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.reports.pdf import report_html
from app.modules.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])
Report = SuccessResponse[dict[str, Any]]


def _range(service: ReportService, date_from: date | None, date_to: date | None):
    end = date_to or service.today()
    return (date_from or end - timedelta(days=29)), end


@router.get("/dashboard", response_model=Report, summary="Dashboard (sections by permission)")
async def dashboard(
    access: TenantAccess = Depends(get_tenant_access), db: AsyncSession = Depends(get_db)
):
    return ok(await ReportService(db, access).dashboard())


@router.get("/sales", response_model=Report)
async def sales_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse_id: uuid.UUID | None = None,
    access: TenantAccess = Depends(require_permission("reports.sales.view")),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db, access)
    return ok(await service.sales_report(*_range(service, date_from, date_to), warehouse_id))


@router.get("/profit", response_model=Report)
async def profit_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse_id: uuid.UUID | None = None,
    access: TenantAccess = Depends(require_permission("reports.financial.view")),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db, access)
    return ok(await service.profit_report(*_range(service, date_from, date_to), warehouse_id))


@router.get("/sales/export", summary="Daily sales as CSV")
async def export_sales_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse_id: uuid.UUID | None = None,
    access: TenantAccess = Depends(require_permission("reports.sales.view")),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db, access)
    report = await service.sales_report(*_range(service, date_from, date_to), warehouse_id)
    return csv_response(
        "sales-by-day.csv",
        ["Date", "Invoices", "Gross sales (incl. tax)"],
        [(d["date"], d["invoice_count"], d["gross_sales"]) for d in report["by_day"]],
    )


@router.get("/profit/export", summary="Daily revenue, cost and gross profit as CSV")
async def export_profit_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse_id: uuid.UUID | None = None,
    access: TenantAccess = Depends(require_permission("reports.financial.view")),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db, access)
    report = await service.profit_report(*_range(service, date_from, date_to), warehouse_id)
    rows = [
        (d["date"], d["invoice_count"], d["revenue"], d["cogs"], d["gross_profit"])
        for d in report["by_day"]
    ]
    s = report["summary"]
    rows.append(("TOTAL", s["invoice_count"], s["revenue"], s["cogs"], s["gross_profit"]))
    if report["expenses"] is not None:
        rows.append(("EXPENSES", "", "", "", s["expenses"]))
        rows.append(("NET PROFIT", "", "", "", s["net_profit"]))
    return csv_response(
        "profit-by-day.csv",
        ["Date", "Invoices", "Revenue (excl. tax)", "Cost of goods sold", "Gross profit"],
        rows,
    )


@router.get("/sales/pdf", summary="Sales report as PDF")
async def sales_report_pdf(
    date_from: date | None = None,
    date_to: date | None = None,
    lang: Literal["ar", "en"] = "ar",
    access: TenantAccess = Depends(require_permission("reports.sales.view")),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db, access)
    start, end = _range(service, date_from, date_to)
    report = await service.sales_report(start, end, None)
    body = report_html("sales", report, access.tenant, start, end, lang)
    return await pdf_response(f"sales-{start}_{end}.pdf", body, lang)


@router.get("/profit/pdf", summary="Profit report as PDF")
async def profit_report_pdf(
    date_from: date | None = None,
    date_to: date | None = None,
    lang: Literal["ar", "en"] = "ar",
    access: TenantAccess = Depends(require_permission("reports.financial.view")),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db, access)
    start, end = _range(service, date_from, date_to)
    report = await service.profit_report(start, end, None)
    body = report_html("profit", report, access.tenant, start, end, lang)
    return await pdf_response(f"profit-{start}_{end}.pdf", body, lang)
