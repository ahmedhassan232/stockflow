"""Read-only analytics. Every query is tenant-filtered (plus RLS) and branch-scoped.

Definitions (documented in docs/business-rules.md):
* revenue      = Σ (subtotal − discount) of completed sales, tax excluded, minus returns
* cogs         = Σ quantity × unit_cost_at_sale (the cost snapshot), minus returns
* gross profit = revenue − cogs
Days are bucketed in the company's time zone. Cancelled sales are excluded entirely.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Date, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.money import ZERO, money
from app.modules.authorization.service import TenantAccess
from app.modules.catalog.models import Product
from app.modules.expenses.models import Expense
from app.modules.inventory.models import StockBalance
from app.modules.inventory.service import warehouse_scope
from app.modules.organization.models import Warehouse
from app.modules.partners.models import Customer
from app.modules.purchasing.models import PurchaseOrder
from app.modules.sales.models import Payment, Sale, SaleItem, SaleReturn, SaleReturnItem
from app.modules.users.models import User

MAX_RANGE_DAYS = 366


def _d(value) -> Decimal:
    return money(Decimal(value or 0))


class ReportService:
    def __init__(self, db: AsyncSession, access: TenantAccess) -> None:
        self.db = db
        self.access = access
        self.tenant_id = access.tenant_id
        try:
            self.tz = ZoneInfo(access.tenant.timezone)
        except Exception:  # noqa: BLE001 - unknown zone name stored for the company
            self.tz = ZoneInfo("UTC")

    # ── helpers ──

    def today(self) -> date:
        return datetime.now(self.tz).date()

    def bounds(self, start: date, end: date) -> tuple[datetime, datetime]:
        if end < start:
            raise AppError("date_to must not be before date_from", code="INVALID_RANGE")
        if (end - start).days > MAX_RANGE_DAYS:
            raise AppError("The date range is too large", code="INVALID_RANGE")
        lo = datetime.combine(start, time.min, self.tz).astimezone(UTC)
        hi = datetime.combine(end + timedelta(days=1), time.min, self.tz).astimezone(UTC)
        return lo, hi

    def _day(self, column) -> ColumnElement:
        return cast(func.timezone(self.tz.key, column), Date)

    def _sales_from(self, lo: datetime, hi: datetime, warehouse_id: uuid.UUID | None):
        where = [
            Sale.tenant_id == self.tenant_id,
            Sale.status == "completed",
            Sale.created_at >= lo,
            Sale.created_at < hi,
            *warehouse_scope(self.access),
        ]
        if warehouse_id:
            where.append(Sale.warehouse_id == warehouse_id)
        join = (Warehouse.tenant_id == Sale.tenant_id) & (Warehouse.id == Sale.warehouse_id)
        return join, where

    def _returns_query(self, lo: datetime, hi: datetime, warehouse_id: uuid.UUID | None, *cols):
        """Returned value (tax excluded) and returned cost, by the date of the return."""
        net = func.sum(
            (SaleItem.line_total - SaleItem.tax_amount)
            * SaleReturnItem.quantity
            / SaleItem.quantity
        )
        cost = func.sum(SaleReturnItem.quantity * SaleItem.unit_cost_at_sale)
        gross = func.sum(SaleReturnItem.line_total)
        where = [
            SaleReturn.tenant_id == self.tenant_id,
            SaleReturn.created_at >= lo,
            SaleReturn.created_at < hi,
            Sale.status == "completed",
            *warehouse_scope(self.access),
        ]
        if warehouse_id:
            where.append(Sale.warehouse_id == warehouse_id)
        return (
            select(*cols, net, cost, gross)
            .select_from(SaleReturnItem)
            .join(
                SaleReturn,
                (SaleReturn.tenant_id == SaleReturnItem.tenant_id)
                & (SaleReturn.id == SaleReturnItem.sale_return_id),
            )
            .join(
                SaleItem,
                (SaleItem.tenant_id == SaleReturnItem.tenant_id)
                & (SaleItem.id == SaleReturnItem.sale_item_id),
            )
            .join(Sale, (Sale.tenant_id == SaleReturn.tenant_id) & (Sale.id == SaleReturn.sale_id))
            .join(
                Warehouse,
                (Warehouse.tenant_id == Sale.tenant_id) & (Warehouse.id == Sale.warehouse_id),
            )
            .where(*where)
        )

    # ── building blocks ──

    async def summary(self, start: date, end: date, warehouse_id: uuid.UUID | None = None) -> dict:
        lo, hi = self.bounds(start, end)
        join, where = self._sales_from(lo, hi, warehouse_id)
        row = (
            await self.db.execute(
                select(
                    func.count(Sale.id),
                    func.sum(Sale.total),
                    func.sum(Sale.subtotal - Sale.discount_amount),
                    func.sum(Sale.tax_amount),
                    func.sum(Sale.discount_amount),
                    func.sum(Sale.cost_total),
                )
                .join(Warehouse, join)
                .where(*where)
            )
        ).one()
        r_net, r_cost, r_gross = (
            await self.db.execute(self._returns_query(lo, hi, warehouse_id))
        ).one()
        revenue = _d(row[2]) - _d(r_net)
        cogs = _d(row[5]) - _d(r_cost)
        profit = revenue - cogs
        return {
            "date_from": start,
            "date_to": end,
            "invoice_count": row[0],
            "gross_sales": _d(row[1]),
            "tax_collected": _d(row[3]),
            "discounts": _d(row[4]),
            "returns": _d(r_gross),
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": profit,
            "margin_percent": money(profit * 100 / revenue) if revenue > ZERO else ZERO,
            "average_invoice": money(_d(row[1]) / row[0]) if row[0] else ZERO,
        }

    async def by_day(
        self, start: date, end: date, warehouse_id: uuid.UUID | None = None
    ) -> list[dict]:
        lo, hi = self.bounds(start, end)
        join, where = self._sales_from(lo, hi, warehouse_id)
        day = self._day(Sale.created_at).label("day")
        sales = await self.db.execute(
            select(
                day,
                func.count(Sale.id),
                func.sum(Sale.total),
                func.sum(Sale.subtotal - Sale.discount_amount),
                func.sum(Sale.cost_total),
            )
            .join(Warehouse, join)
            .where(*where)
            .group_by(literal_column("day"))
        )
        rday = self._day(SaleReturn.created_at).label("day")
        returns = await self.db.execute(
            self._returns_query(lo, hi, warehouse_id, rday).group_by(literal_column("day"))
        )
        days = {
            start + timedelta(days=n): {
                "date": start + timedelta(days=n),
                "invoice_count": 0,
                "gross_sales": ZERO,
                "revenue": ZERO,
                "cogs": ZERO,
            }
            for n in range((end - start).days + 1)
        }
        for d, count, gross, net, cost in sales.all():
            days[d].update(
                invoice_count=count, gross_sales=_d(gross), revenue=_d(net), cogs=_d(cost)
            )
        for d, net, cost, _gross in returns.all():
            days[d]["revenue"] -= _d(net)
            days[d]["cogs"] -= _d(cost)
        out = []
        for row in days.values():
            row["gross_sales"] = _d(row["gross_sales"])
            row["revenue"], row["cogs"] = _d(row["revenue"]), _d(row["cogs"])
            row["gross_profit"] = row["revenue"] - row["cogs"]
            out.append(row)
        return out

    async def top_products(
        self, start: date, end: date, warehouse_id: uuid.UUID | None = None, limit: int = 10
    ) -> list[dict]:
        lo, hi = self.bounds(start, end)
        join, where = self._sales_from(lo, hi, warehouse_id)
        net_qty = SaleItem.quantity - SaleItem.returned_quantity
        share = net_qty / SaleItem.quantity
        revenue = func.sum((SaleItem.line_total - SaleItem.tax_amount) * share)
        rows = await self.db.execute(
            select(
                SaleItem.product_id,
                func.max(Product.name),
                func.max(Product.sku),
                func.sum(net_qty),
                revenue,
                func.sum(net_qty * SaleItem.unit_cost_at_sale),
            )
            .select_from(SaleItem)
            .join(Sale, (Sale.tenant_id == SaleItem.tenant_id) & (Sale.id == SaleItem.sale_id))
            .join(Warehouse, join)
            .join(
                Product,
                (Product.tenant_id == SaleItem.tenant_id) & (Product.id == SaleItem.product_id),
            )
            .where(*where)
            .group_by(SaleItem.product_id)
            .having(func.sum(net_qty) > 0)
            .order_by(revenue.desc(), SaleItem.product_id)
            .limit(limit)
        )
        return [
            {
                "product_id": pid,
                "name": name,
                "sku": sku,
                "quantity": Decimal(quantity),
                "revenue": _d(rev),
                "gross_profit": _d(rev) - _d(cost),
            }
            for pid, name, sku, quantity, rev, cost in rows.all()
        ]

    async def by_payment_method(
        self, start: date, end: date, warehouse_id: uuid.UUID | None = None
    ) -> list[dict]:
        """Cash actually collected in the period (refunds subtracted), any invoice date."""
        lo, hi = self.bounds(start, end)
        where = [
            Payment.tenant_id == self.tenant_id,
            Payment.sale_id.is_not(None),
            Payment.created_at >= lo,
            Payment.created_at < hi,
            *warehouse_scope(self.access),
        ]
        if warehouse_id:
            where.append(Sale.warehouse_id == warehouse_id)
        rows = await self.db.execute(
            select(Payment.method, Payment.direction, func.sum(Payment.amount))
            .join(Sale, (Sale.tenant_id == Payment.tenant_id) & (Sale.id == Payment.sale_id))
            .join(
                Warehouse,
                (Warehouse.tenant_id == Sale.tenant_id) & (Warehouse.id == Sale.warehouse_id),
            )
            .where(*where)
            .group_by(Payment.method, Payment.direction)
        )
        totals: dict[str, dict] = {}
        for method, direction, amount in rows.all():
            entry = totals.setdefault(
                method, {"method": method, "received": ZERO, "refunded": ZERO, "net": ZERO}
            )
            entry["received" if direction == "in" else "refunded"] = _d(amount)
        for entry in totals.values():
            entry["net"] = entry["received"] - entry["refunded"]
        return sorted(totals.values(), key=lambda e: e["net"], reverse=True)

    async def by_cashier(
        self, start: date, end: date, warehouse_id: uuid.UUID | None = None
    ) -> list[dict]:
        lo, hi = self.bounds(start, end)
        join, where = self._sales_from(lo, hi, warehouse_id)
        rows = await self.db.execute(
            select(
                Sale.created_by, func.max(User.full_name), func.count(Sale.id), func.sum(Sale.total)
            )
            .join(Warehouse, join)
            .join(User, User.id == Sale.created_by)
            .where(*where)
            .group_by(Sale.created_by)
            .order_by(func.sum(Sale.total).desc())
        )
        return [
            {"user_id": uid, "name": name, "invoice_count": count, "gross_sales": _d(total)}
            for uid, name, count, total in rows.all()
        ]

    async def receivables(self, limit: int = 20) -> dict:
        due = Sale.total - Sale.returned_amount - Sale.paid_amount
        where = [
            Sale.tenant_id == self.tenant_id,
            Sale.status == "completed",
            due > 0,
            *warehouse_scope(self.access),
        ]
        join = (Warehouse.tenant_id == Sale.tenant_id) & (Warehouse.id == Sale.warehouse_id)
        total = (
            await self.db.execute(select(func.sum(due)).join(Warehouse, join).where(*where))
        ).scalar_one()
        rows = await self.db.execute(
            select(Sale.customer_id, func.max(Customer.name), func.count(Sale.id), func.sum(due))
            .join(Warehouse, join)
            .join(
                Customer, (Customer.tenant_id == Sale.tenant_id) & (Customer.id == Sale.customer_id)
            )
            .where(*where)
            .group_by(Sale.customer_id)
            .order_by(func.sum(due).desc())
            .limit(limit)
        )
        return {
            "total": _d(total),
            "customers": [
                {"customer_id": cid, "name": name, "invoice_count": count, "balance": _d(balance)}
                for cid, name, count, balance in rows.all()
            ],
        }

    async def payables_total(self) -> Decimal:
        total = await self.db.execute(
            select(func.sum(PurchaseOrder.total - PurchaseOrder.paid_amount))
            .join(
                Warehouse,
                (Warehouse.tenant_id == PurchaseOrder.tenant_id)
                & (Warehouse.id == PurchaseOrder.warehouse_id),
            )
            .where(
                PurchaseOrder.tenant_id == self.tenant_id,
                PurchaseOrder.status.in_(("partially_received", "received")),
                *warehouse_scope(self.access),
            )
        )
        return _d(total.scalar_one())

    async def stock_snapshot(self) -> dict:
        join = (Warehouse.tenant_id == StockBalance.tenant_id) & (
            Warehouse.id == StockBalance.warehouse_id
        )
        pjoin = (Product.tenant_id == StockBalance.tenant_id) & (
            Product.id == StockBalance.product_id
        )
        where = [StockBalance.tenant_id == self.tenant_id, *warehouse_scope(self.access)]
        value = (
            await self.db.execute(
                select(func.sum(StockBalance.quantity * Product.average_cost))
                .join(Warehouse, join)
                .join(Product, pjoin)
                .where(*where)
            )
        ).scalar_one()
        low = (
            await self.db.execute(
                select(func.count())
                .select_from(StockBalance)
                .join(Warehouse, join)
                .join(Product, pjoin)
                .where(
                    *where,
                    Product.is_active.is_(True),
                    StockBalance.minimum_stock_level > 0,
                    StockBalance.quantity <= StockBalance.minimum_stock_level,
                )
            )
        ).scalar_one()
        products = (
            await self.db.execute(
                select(func.count())
                .select_from(Product)
                .where(Product.tenant_id == self.tenant_id, Product.is_active.is_(True))
            )
        ).scalar_one()
        return {"stock_value": _d(value), "low_stock_count": low, "active_products": products}

    # ── composed reports ──

    async def dashboard(self) -> dict:
        """Each section is included only if the caller holds the matching permission;
        otherwise it is null (the UI hides the widget, the data never leaves the server)."""
        can = self.access.has
        today = self.today()
        month_start = today.replace(day=1)
        chart_start = today - timedelta(days=13)
        out: dict = {"today": today, "currency": self.access.tenant.currency}
        sales = can("reports.sales.view")
        financial = can("reports.financial.view")

        def trim(summary: dict) -> dict:
            keys = ["invoice_count", "gross_sales", "returns", "average_invoice"]
            if financial:
                keys += ["revenue", "cogs", "gross_profit", "margin_percent"]
            return {k: summary[k] for k in keys}

        out["sales_today"] = trim(await self.summary(today, today)) if sales else None
        out["sales_month"] = trim(await self.summary(month_start, today)) if sales else None
        if sales:
            series = await self.by_day(chart_start, today)
            if not financial:
                for row in series:
                    for key in ("revenue", "cogs", "gross_profit"):
                        row.pop(key)
            out["sales_by_day"] = series
            out["top_products"] = [
                {k: v for k, v in p.items() if financial or k != "gross_profit"}
                for p in await self.top_products(today - timedelta(days=29), today, limit=5)
            ]
            out["receivables_total"] = (await self.receivables(limit=1))["total"]
        else:
            out["sales_by_day"] = out["top_products"] = out["receivables_total"] = None
        out["payables_total"] = await self.payables_total() if financial else None
        if can("inventory.view"):
            snapshot = await self.stock_snapshot()
            if not can("reports.inventory.view"):
                snapshot["stock_value"] = None
            out["inventory"] = snapshot
        else:
            out["inventory"] = None
        return out

    async def sales_report(self, start: date, end: date, warehouse_id: uuid.UUID | None) -> dict:
        summary = await self.summary(start, end, warehouse_id)
        for key in ("revenue", "cogs", "gross_profit", "margin_percent"):
            summary.pop(key)  # profit figures need reports.financial.view
        days = await self.by_day(start, end, warehouse_id)
        products = await self.top_products(start, end, warehouse_id, limit=20)
        for row in days:
            for key in ("revenue", "cogs", "gross_profit"):
                row.pop(key)
        for row in products:
            row.pop("gross_profit")
        return {
            "summary": summary,
            "by_day": days,
            "top_products": products,
            "by_payment_method": await self.by_payment_method(start, end, warehouse_id),
            "by_cashier": await self.by_cashier(start, end, warehouse_id),
        }

    async def expenses(self, start: date, end: date) -> dict:
        """Active expenses dated inside the range (expense_date is already a local date)."""
        rows = (
            await self.db.execute(
                select(Expense.category, func.sum(Expense.amount))
                .where(
                    Expense.tenant_id == self.access.tenant_id,
                    Expense.status == "active",
                    Expense.expense_date >= start,
                    Expense.expense_date <= end,
                )
                .group_by(Expense.category)
                .order_by(func.sum(Expense.amount).desc())
            )
        ).all()
        by_category = [{"category": c, "amount": _d(a)} for c, a in rows]
        return {
            "total": money(sum((r["amount"] for r in by_category), ZERO)),
            "by_category": by_category,
        }

    async def profit_report(self, start: date, end: date, warehouse_id: uuid.UUID | None) -> dict:
        summary = await self.summary(start, end, warehouse_id)
        # Expenses belong to the company, not to a warehouse: when the report is filtered
        # by warehouse a net profit would be misleading, so it is omitted.
        expenses = await self.expenses(start, end) if warehouse_id is None else None
        if expenses is not None:
            summary["expenses"] = expenses["total"]
            summary["net_profit"] = money(summary["gross_profit"] - expenses["total"])
        return {
            "summary": summary,
            "expenses": expenses,
            "by_day": await self.by_day(start, end, warehouse_id),
            "top_products": await self.top_products(start, end, warehouse_id, limit=20),
            "receivables": await self.receivables(),
            "payables_total": await self.payables_total(),
        }
