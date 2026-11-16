import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import ensure_exists
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.money import ZERO, money
from app.core.pagination import PageParams
from app.db.repository import like_pattern
from app.modules.activity.service import audit, notify_if_low_stock
from app.modules.authorization.service import TenantAccess
from app.modules.inventory.ledger import StockLedger
from app.modules.inventory.service import get_accessible_warehouse, warehouse_scope
from app.modules.organization.models import Warehouse
from app.modules.partners.models import Customer
from app.modules.sales.calc import line_amounts, proportion
from app.modules.sales.models import Payment, Sale, SaleItem, SaleReturn, SaleReturnItem
from app.modules.sales.schemas import (
    PaymentIn,
    PaymentOut,
    SaleCreate,
    SaleDetail,
    SaleItemOut,
    SaleOut,
    SaleReturnCreate,
)
from app.modules.settings.service import get_company_settings, next_document_number
from app.modules.users.models import User


def _fill(out: SaleOut, sale: Sale) -> None:
    net = sale.total - sale.returned_amount
    out.balance_due = money(max(net - sale.paid_amount, ZERO))
    if sale.status == "cancelled":
        out.payment_status = "cancelled"
    elif out.balance_due == ZERO:
        out.payment_status = "paid"
    elif sale.paid_amount > ZERO:
        out.payment_status = "partial"
    else:
        out.payment_status = "unpaid"


class SaleService:
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

    # ── reads ──

    async def _load(self, sale_id: uuid.UUID, *, lock: bool = False) -> Sale:
        stmt = select(Sale).where(Sale.tenant_id == self.tenant_id, Sale.id == sale_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        sale = (await self.db.execute(stmt)).scalar_one_or_none()
        if sale is None:
            raise NotFoundError("Sale not found")
        await get_accessible_warehouse(
            self.db, self.access, sale.warehouse_id, must_be_active=False
        )
        return sale

    async def _items(self, sale_id: uuid.UUID) -> list[SaleItem]:
        rows = await self.db.execute(
            select(SaleItem)
            .where(SaleItem.tenant_id == self.tenant_id, SaleItem.sale_id == sale_id)
            .order_by(SaleItem.line_no)
            .execution_options(populate_existing=True)
        )
        return list(rows.scalars().all())

    async def detail(self, sale_id: uuid.UUID, sale: Sale | None = None) -> SaleDetail:
        sale = sale or await self._load(sale_id)
        await self.db.refresh(sale)
        out = SaleDetail.model_validate(sale)
        _fill(out, sale)
        out.items = [SaleItemOut.model_validate(i) for i in await self._items(sale.id)]
        payments = await self.db.execute(
            select(Payment)
            .where(Payment.tenant_id == self.tenant_id, Payment.sale_id == sale.id)
            .order_by(Payment.created_at, Payment.id)
        )
        out.payments = [PaymentOut.model_validate(p) for p in payments.scalars().all()]
        if sale.customer_id:
            customer = await self.db.get(Customer, sale.customer_id)
            out.customer_name = customer.name if customer else None
        warehouse = await self.db.get(Warehouse, sale.warehouse_id)
        out.warehouse_name = warehouse.name if warehouse else ""
        cashier = await self.db.get(User, sale.created_by)
        out.cashier_name = cashier.full_name if cashier else ""
        return out

    async def search(
        self,
        page: PageParams,
        *,
        q: str | None,
        status: str | None,
        customer_id: uuid.UUID | None,
        warehouse_id: uuid.UUID | None,
        unpaid_only: bool,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[SaleOut], int]:
        where = [Sale.tenant_id == self.tenant_id, *warehouse_scope(self.access)]
        if q:
            pattern = like_pattern(q)
            where.append(
                Sale.number.ilike(pattern, escape="\\") | Customer.name.ilike(pattern, escape="\\")
            )
        if status:
            where.append(Sale.status == status)
        if customer_id:
            where.append(Sale.customer_id == customer_id)
        if warehouse_id:
            where.append(Sale.warehouse_id == warehouse_id)
        if unpaid_only:
            where += [
                Sale.status == "completed",
                Sale.total - Sale.returned_amount > Sale.paid_amount,
            ]
        if date_from:
            where.append(Sale.created_at >= date_from)
        if date_to:
            where.append(Sale.created_at <= date_to)
        base = (
            select(Sale, Customer.name, Warehouse.name)
            .join(
                Warehouse,
                (Warehouse.tenant_id == Sale.tenant_id) & (Warehouse.id == Sale.warehouse_id),
            )
            .outerjoin(
                Customer,
                (Customer.tenant_id == Sale.tenant_id) & (Customer.id == Sale.customer_id),
            )
            .where(*where)
        )
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = await self.db.execute(
            base.order_by(Sale.created_at.desc(), Sale.id).limit(page.page_size).offset(page.offset)
        )
        items = []
        for sale, customer_name, warehouse_name in rows.all():
            out = SaleOut.model_validate(sale)
            out.customer_name, out.warehouse_name = customer_name, warehouse_name
            _fill(out, sale)
            items.append(out)
        return items, total

    # ── posting a sale ──

    async def create(self, data: SaleCreate) -> SaleDetail:
        """One transaction: number, invoice, lines, stock movements, payments. Any failure
        (e.g. insufficient stock on the last line) rolls everything back."""
        await get_accessible_warehouse(self.db, self.access, data.warehouse_id)
        await ensure_exists(
            self.db, self.tenant_id, Customer, data.customer_id, "Customer", must_be_active=True
        )
        ledger = await self._ledger()
        products = await ledger.lock_products(i.product_id for i in data.items)
        for item in data.items:
            product = products.get(item.product_id)
            if product is None:
                raise AppError(
                    "Product not found",
                    code="INVALID_REFERENCE",
                    details={"id": str(item.product_id)},
                )
            if not product.is_active:
                raise AppError(
                    "Product is inactive",
                    code="INACTIVE_REFERENCE",
                    details={"id": str(item.product_id)},
                )
        balances = await ledger.lock_balances(
            (data.warehouse_id, i.product_id)
            for i in data.items
            if products[i.product_id].track_inventory
        )

        # Authoritative totals.
        lines = []
        subtotal = discount = tax = cost_total = ZERO
        for item in data.items:
            product = products[item.product_id]
            price = product.selling_price if item.unit_price is None else item.unit_price
            amounts = line_amounts(item.quantity, price, product.tax_rate, item.discount_amount)
            subtotal += amounts.gross
            discount += amounts.discount
            tax += amounts.tax
            cost_total += money(item.quantity * product.average_cost)
            lines.append((item, product, price, amounts))
        total = subtotal - discount + tax

        tendered = sum((p.amount for p in data.payments), ZERO)
        change = money(max(tendered - total, ZERO))
        if change > ZERO and not any(p.method == "cash" for p in data.payments):
            raise AppError("Only cash payments may exceed the total", code="OVERPAYMENT")
        paid = min(tendered, total)
        if paid < total and data.customer_id is None:
            raise AppError(
                "A customer is required when the invoice is not fully paid",
                code="CUSTOMER_REQUIRED",
                details={"total": str(total), "paid": str(paid)},
            )

        sale = Sale(
            tenant_id=self.tenant_id,
            number=await next_document_number(self.db, self.tenant_id, "sale", "INV"),
            customer_id=data.customer_id,
            warehouse_id=data.warehouse_id,
            subtotal=subtotal,
            discount_amount=discount,
            tax_amount=tax,
            total=total,
            cost_total=cost_total,
            paid_amount=paid,
            notes=data.notes,
            created_by=self.access.user_id,
        )
        self.db.add(sale)
        await self.db.flush()

        for line_no, (item, product, price, amounts) in enumerate(lines, start=1):
            self.db.add(
                SaleItem(
                    tenant_id=self.tenant_id,
                    sale_id=sale.id,
                    line_no=line_no,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_price=price,
                    discount_amount=amounts.discount,
                    tax_rate=product.tax_rate,
                    tax_amount=amounts.tax,
                    line_total=amounts.total,
                    unit_cost_at_sale=product.average_cost,
                )
            )
            if product.track_inventory:
                balance = balances[(data.warehouse_id, product.id)]
                await ledger.move(
                    balance,
                    movement_type="sale",
                    quantity=item.quantity,
                    unit_cost=product.average_cost,
                    reference_type="sale",
                    reference_id=sale.id,
                    line_no=line_no,
                )
                await notify_if_low_stock(self.db, balance, product)

        # Record payments; cash absorbs the change so that sum(payments) == paid.
        remaining = paid
        for payment in sorted(data.payments, key=lambda p: p.method == "cash"):
            amount = min(payment.amount, remaining)
            if amount <= ZERO:
                continue
            remaining -= amount
            self.db.add(
                Payment(
                    tenant_id=self.tenant_id,
                    direction="in",
                    method=payment.method,
                    amount=amount,
                    sale_id=sale.id,
                    reference=payment.reference,
                    created_by=self.access.user_id,
                )
            )
        await self.db.flush()
        audit(
            self.db,
            self.access,
            "sale.created",
            "sale",
            sale.id,
            sale.number,
            {"total": str(total)},
        )
        out = await self.detail(sale.id, sale)
        out.change_due = change
        return out

    # ── after-sale operations ──

    async def pay(self, sale_id: uuid.UUID, data: PaymentIn) -> SaleDetail:
        sale = await self._load(sale_id, lock=True)
        if sale.status != "completed":
            raise ConflictError("This sale cannot be paid", code="INVALID_STATUS")
        due = sale.total - sale.returned_amount - sale.paid_amount
        if data.amount > due:
            raise ConflictError(
                "Payment exceeds the balance due", code="OVERPAYMENT", details={"due": str(due)}
            )
        self.db.add(
            Payment(
                tenant_id=self.tenant_id,
                direction="in",
                method=data.method,
                amount=money(data.amount),
                sale_id=sale.id,
                reference=data.reference,
                created_by=self.access.user_id,
            )
        )
        sale.paid_amount += data.amount
        await self.db.flush()
        return await self.detail(sale.id, sale)

    async def _refund(self, sale: Sale, amount: Decimal, reference: str) -> None:
        if amount <= ZERO:
            return
        self.db.add(
            Payment(
                tenant_id=self.tenant_id,
                direction="out",
                method="cash",
                amount=amount,
                sale_id=sale.id,
                reference=reference,
                created_by=self.access.user_id,
            )
        )
        sale.paid_amount -= amount

    async def _restock(
        self,
        sale: Sale,
        lines: list[tuple[SaleItem, Decimal]],
        *,
        reference_type: str,
        reference_id: uuid.UUID,
        reason: str,
    ) -> None:
        ledger = await self._ledger()
        products = await ledger.lock_products(i.product_id for i, _ in lines)
        tracked = [(i, q) for i, q in lines if products[i.product_id].track_inventory]
        balances = await ledger.lock_balances((sale.warehouse_id, i.product_id) for i, _ in tracked)
        for item, quantity in tracked:
            # Goods come back at the cost they left with.
            await ledger.apply_receipt_cost(
                products[item.product_id], quantity, item.unit_cost_at_sale
            )
            await ledger.move(
                balances[(sale.warehouse_id, item.product_id)],
                movement_type="sale_return",
                quantity=quantity,
                unit_cost=item.unit_cost_at_sale,
                reference_type=reference_type,
                reference_id=reference_id,
                line_no=item.line_no,
                reason=reason,
            )

    async def return_items(self, sale_id: uuid.UUID, data: SaleReturnCreate) -> SaleDetail:
        sale = await self._load(sale_id, lock=True)  # serialises returns of one invoice
        if sale.status != "completed":
            raise ConflictError("This sale cannot be returned", code="INVALID_STATUS")
        by_id = {i.id: i for i in await self._items(sale.id)}
        lines: list[tuple[SaleItem, Decimal]] = []
        for line in data.items:
            item = by_id.get(line.sale_item_id)
            if item is None:
                raise AppError(
                    "Item does not belong to this sale",
                    code="INVALID_REFERENCE",
                    details={"id": str(line.sale_item_id)},
                )
            returnable = item.quantity - item.returned_quantity
            if line.quantity > returnable:
                raise ConflictError(
                    "Cannot return more than was sold",
                    code="OVER_RETURN",
                    details={"sale_item_id": str(item.id), "returnable": str(returnable)},
                )
            lines.append((item, line.quantity))

        values: list[Decimal] = []
        total = cost_total = ZERO
        for item, quantity in lines:
            if quantity == item.quantity - item.returned_quantity:
                # last piece: take the exact remainder so rounding never leaks a cent
                already = proportion(item.line_total, item.returned_quantity, item.quantity)
                value = item.line_total - already
            else:
                value = proportion(item.line_total, quantity, item.quantity)
            values.append(value)
            total += value
            cost_total += money(quantity * item.unit_cost_at_sale)
        # Refund whatever the customer has paid beyond what the invoice is now worth.
        worth = sale.total - sale.returned_amount - total
        refund = money(max(sale.paid_amount - worth, ZERO))

        # sale_returns is append-only, so the document is inserted once, complete.
        doc = SaleReturn(
            tenant_id=self.tenant_id,
            number=await next_document_number(self.db, self.tenant_id, "sale_return", "SRN"),
            sale_id=sale.id,
            total=total,
            cost_total=cost_total,
            refund_amount=refund,
            reason=data.reason,
            created_by=self.access.user_id,
        )
        self.db.add(doc)
        await self.db.flush()
        for line_no, ((item, quantity), value) in enumerate(zip(lines, values, strict=True), 1):
            self.db.add(
                SaleReturnItem(
                    tenant_id=self.tenant_id,
                    sale_return_id=doc.id,
                    line_no=line_no,
                    sale_item_id=item.id,
                    product_id=item.product_id,
                    quantity=quantity,
                    line_total=value,
                )
            )
        await self._restock(
            sale, lines, reference_type="sale_return", reference_id=doc.id, reason=data.reason
        )
        for item, quantity in lines:
            item.returned_quantity += quantity
        sale.returned_amount += total
        await self._refund(sale, refund, doc.number)
        await self.db.flush()
        audit(
            self.db,
            self.access,
            "sale.returned",
            "sale",
            sale.id,
            f"{sale.number} / {doc.number}",
            {"total": str(total), "refund": str(refund), "reason": data.reason},
        )
        out = await self.detail(sale.id, sale)
        out.refund_amount = refund
        return out

    async def cancel(self, sale_id: uuid.UUID, reason: str) -> SaleDetail:
        """Voids the whole invoice: all stock comes back and all money is refunded."""
        sale = await self._load(sale_id, lock=True)
        if sale.status != "completed":
            raise ConflictError("This sale is already cancelled", code="INVALID_STATUS")
        if sale.returned_amount > ZERO:
            raise ConflictError(
                "A sale with returns cannot be cancelled; return the remaining items instead",
                code="HAS_RETURNS",
            )
        items = await self._items(sale.id)
        await self._restock(
            sale,
            [(i, i.quantity) for i in items],
            reference_type="sale_cancel",
            reference_id=sale.id,
            reason=reason,
        )
        refund = sale.paid_amount
        await self._refund(sale, refund, f"cancel {sale.number}")
        sale.status = "cancelled"
        await self.db.flush()
        audit(
            self.db,
            self.access,
            "sale.cancelled",
            "sale",
            sale.id,
            sale.number,
            {"reason": reason, "refund": str(refund)},
        )
        out = await self.detail(sale.id, sale)
        out.refund_amount = refund
        return out
