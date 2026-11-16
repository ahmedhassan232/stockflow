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
from app.modules.activity.service import audit
from app.modules.authorization.service import TenantAccess
from app.modules.catalog.models import Product
from app.modules.inventory.ledger import StockLedger
from app.modules.inventory.service import get_accessible_warehouse, warehouse_scope
from app.modules.organization.models import Warehouse
from app.modules.partners.models import Supplier
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
)
from app.modules.purchasing.schemas import (
    DocLineIn,
    PaymentIn,
    PurchaseCreate,
    PurchaseDetail,
    PurchaseItemOut,
    PurchaseOut,
    PurchaseReturnRequest,
    ReceiveRequest,
)
from app.modules.sales.calc import line_amounts
from app.modules.sales.models import Payment
from app.modules.settings.service import get_company_settings, next_document_number


class PurchaseService:
    def __init__(self, db: AsyncSession, access: TenantAccess) -> None:
        self.db = db
        self.access = access
        self.tenant_id = access.tenant_id

    # ── loading ──

    async def _load(self, po_id: uuid.UUID, *, lock: bool = False) -> PurchaseOrder:
        stmt = select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == self.tenant_id, PurchaseOrder.id == po_id
        )
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        po = (await self.db.execute(stmt)).scalar_one_or_none()
        if po is None:
            raise NotFoundError("Purchase order not found")
        # Branch scope: a purchase of a warehouse outside the caller's branches is hidden.
        await get_accessible_warehouse(self.db, self.access, po.warehouse_id, must_be_active=False)
        return po

    async def _items(self, po_id: uuid.UUID) -> list[PurchaseOrderItem]:
        rows = await self.db.execute(
            select(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.tenant_id == self.tenant_id,
                PurchaseOrderItem.purchase_order_id == po_id,
            )
            .order_by(PurchaseOrderItem.line_no)
            .execution_options(populate_existing=True)
        )
        return list(rows.scalars().all())

    async def detail(self, po_id: uuid.UUID, po: PurchaseOrder | None = None) -> PurchaseDetail:
        po = po or await self._load(po_id)
        await self.db.refresh(po)
        items = await self._items(po.id)
        products = {
            p.id: p
            for p in (
                await self.db.execute(
                    select(Product).where(
                        Product.tenant_id == self.tenant_id,
                        Product.id.in_([i.product_id for i in items]),
                    )
                )
            ).scalars()
        }
        supplier = await self.db.get(Supplier, po.supplier_id)
        warehouse = await self.db.get(Warehouse, po.warehouse_id)
        out = PurchaseDetail.model_validate(po)
        out.supplier_name = supplier.name if supplier else ""
        out.warehouse_name = warehouse.name if warehouse else ""
        out.balance_due = po.total - po.paid_amount
        for item in items:
            line = PurchaseItemOut.model_validate(item)
            line.product_name = products[item.product_id].name
            line.sku = products[item.product_id].sku
            out.items.append(line)
        return out

    async def search(
        self,
        page: PageParams,
        *,
        q: str | None,
        status: str | None,
        supplier_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[PurchaseOut], int]:
        where = [PurchaseOrder.tenant_id == self.tenant_id, *warehouse_scope(self.access)]
        if q:
            pattern = like_pattern(q)
            where.append(
                PurchaseOrder.number.ilike(pattern, escape="\\")
                | Supplier.name.ilike(pattern, escape="\\")
            )
        if status:
            where.append(PurchaseOrder.status == status)
        if supplier_id:
            where.append(PurchaseOrder.supplier_id == supplier_id)
        if date_from:
            where.append(PurchaseOrder.created_at >= date_from)
        if date_to:
            where.append(PurchaseOrder.created_at <= date_to)
        base = (
            select(PurchaseOrder, Supplier.name, Warehouse.name)
            .join(
                Supplier,
                (Supplier.tenant_id == PurchaseOrder.tenant_id)
                & (Supplier.id == PurchaseOrder.supplier_id),
            )
            .join(
                Warehouse,
                (Warehouse.tenant_id == PurchaseOrder.tenant_id)
                & (Warehouse.id == PurchaseOrder.warehouse_id),
            )
            .where(*where)
        )
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = await self.db.execute(
            base.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id)
            .limit(page.page_size)
            .offset(page.offset)
        )
        items = []
        for po, supplier_name, warehouse_name in rows.all():
            out = PurchaseOut.model_validate(po)
            out.supplier_name, out.warehouse_name = supplier_name, warehouse_name
            out.balance_due = po.total - po.paid_amount
            items.append(out)
        return items, total

    # ── writes ──

    async def create(self, data: PurchaseCreate) -> PurchaseDetail:
        await ensure_exists(
            self.db, self.tenant_id, Supplier, data.supplier_id, "Supplier", must_be_active=True
        )
        await get_accessible_warehouse(self.db, self.access, data.warehouse_id)
        for item in data.items:
            product = await ensure_exists(
                self.db, self.tenant_id, Product, item.product_id, "Product", must_be_active=True
            )
            if not product.track_inventory:
                raise AppError(
                    "This product does not track inventory",
                    code="NOT_TRACKED",
                    details={"product_id": str(product.id)},
                )
        po = PurchaseOrder(
            tenant_id=self.tenant_id,
            number=await next_document_number(self.db, self.tenant_id, "purchase_order", "PO"),
            supplier_id=data.supplier_id,
            warehouse_id=data.warehouse_id,
            status=data.status,
            notes=data.notes,
            created_by=self.access.user_id,
        )
        self.db.add(po)
        await self.db.flush()
        subtotal = tax = ZERO
        for line_no, item in enumerate(data.items, start=1):
            amounts = line_amounts(item.quantity, item.unit_cost, item.tax_rate)
            subtotal += amounts.gross
            tax += amounts.tax
            self.db.add(
                PurchaseOrderItem(
                    tenant_id=self.tenant_id,
                    purchase_order_id=po.id,
                    line_no=line_no,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    tax_rate=item.tax_rate,
                    tax_amount=amounts.tax,
                    line_total=amounts.total,
                )
            )
        po.subtotal, po.tax_amount, po.total = subtotal, tax, subtotal + tax
        await self.db.flush()
        audit(self.db, self.access, "purchase.created", "purchase_order", po.id, po.number)
        return await self.detail(po.id, po)

    async def confirm(self, po_id: uuid.UUID) -> PurchaseDetail:
        po = await self._load(po_id, lock=True)
        if po.status != "draft":
            raise ConflictError("Only a draft can be confirmed", code="INVALID_STATUS")
        po.status = "ordered"
        await self.db.flush()
        return await self.detail(po.id, po)

    async def cancel(self, po_id: uuid.UUID) -> PurchaseDetail:
        po = await self._load(po_id, lock=True)
        if po.status not in ("draft", "ordered"):
            raise ConflictError(
                "A purchase with received goods cannot be cancelled; return the goods instead",
                code="INVALID_STATUS",
            )
        if po.paid_amount > ZERO:
            raise ConflictError("This purchase already has payments", code="HAS_PAYMENTS")
        po.status = "cancelled"
        await self.db.flush()
        audit(self.db, self.access, "purchase.cancelled", "purchase_order", po.id, po.number)
        return await self.detail(po.id, po)

    async def _document(self, po: PurchaseOrder, kind: str, notes: str | None) -> PurchaseReceipt:
        doc_type, prefix = (
            ("purchase_receipt", "GRN") if kind == "receipt" else ("purchase_return", "PRN")
        )
        doc = PurchaseReceipt(
            tenant_id=self.tenant_id,
            number=await next_document_number(self.db, self.tenant_id, doc_type, prefix),
            kind=kind,
            purchase_order_id=po.id,
            warehouse_id=po.warehouse_id,
            notes=notes,
            created_by=self.access.user_id,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    def _match(
        self, lines: list[DocLineIn], items: list[PurchaseOrderItem]
    ) -> list[tuple[PurchaseOrderItem, Decimal]]:
        by_id = {i.id: i for i in items}
        matched = []
        for line in lines:
            item = by_id.get(line.item_id)
            if item is None:
                raise AppError(
                    "Item does not belong to this purchase order",
                    code="INVALID_REFERENCE",
                    details={"id": str(line.item_id)},
                )
            matched.append((item, line.quantity))
        return matched

    async def receive(self, po_id: uuid.UUID, data: ReceiveRequest) -> PurchaseDetail:
        """Atomic goods receipt: stock in + weighted average cost + PO progress."""
        po = await self._load(po_id, lock=True)  # serialises concurrent receipts of one PO
        if po.status not in ("ordered", "partially_received"):
            raise ConflictError(
                "This purchase order cannot receive goods in its current status",
                code="INVALID_STATUS",
                details={"status": po.status},
            )
        await get_accessible_warehouse(self.db, self.access, po.warehouse_id)
        items = await self._items(po.id)
        if data.items is None:
            lines = [(i, i.quantity - i.received_quantity) for i in items]
            lines = [(i, q) for i, q in lines if q > ZERO]
        else:
            lines = self._match(data.items, items)
        for item, quantity in lines:
            if quantity > item.quantity - item.received_quantity:
                raise ConflictError(
                    "Cannot receive more than the outstanding quantity",
                    code="OVER_RECEIPT",
                    details={
                        "item_id": str(item.id),
                        "outstanding": str(item.quantity - item.received_quantity),
                    },
                )
        ledger = StockLedger(self.db, self.tenant_id, self.access.user_id)
        products = await ledger.lock_products(i.product_id for i, _ in lines)
        balances = await ledger.lock_balances((po.warehouse_id, i.product_id) for i, _ in lines)
        receipt = await self._document(po, "receipt", data.notes)
        for line_no, (item, quantity) in enumerate(lines, start=1):
            product = products[item.product_id]
            await ledger.apply_receipt_cost(product, quantity, item.unit_cost)
            product.purchase_price = item.unit_cost
            await ledger.move(
                balances[(po.warehouse_id, item.product_id)],
                movement_type="purchase_receipt",
                quantity=quantity,
                unit_cost=item.unit_cost,
                reference_type="purchase_receipt",
                reference_id=receipt.id,
                line_no=line_no,
            )
            item.received_quantity += quantity
            self.db.add(
                PurchaseReceiptItem(
                    tenant_id=self.tenant_id,
                    purchase_receipt_id=receipt.id,
                    line_no=line_no,
                    purchase_order_item_id=item.id,
                    product_id=item.product_id,
                    quantity=quantity,
                    unit_cost=item.unit_cost,
                )
            )
        done = all(i.received_quantity >= i.quantity for i in items)
        po.status = "received" if done else "partially_received"
        await self.db.flush()
        audit(
            self.db,
            self.access,
            "purchase.received",
            "purchase_order",
            po.id,
            f"{po.number} / {receipt.number}",
        )
        return await self.detail(po.id, po)

    async def return_goods(self, po_id: uuid.UUID, data: PurchaseReturnRequest) -> PurchaseDetail:
        """Sends received goods back to the supplier: stock out at the purchase cost.
        The moving average cost is left unchanged (documented simplification)."""
        po = await self._load(po_id, lock=True)
        if po.status not in ("partially_received", "received"):
            raise ConflictError("Nothing has been received yet", code="INVALID_STATUS")
        await get_accessible_warehouse(self.db, self.access, po.warehouse_id)
        lines = self._match(data.items, await self._items(po.id))
        for item, quantity in lines:
            if quantity > item.received_quantity - item.returned_quantity:
                raise ConflictError(
                    "Cannot return more than was received",
                    code="OVER_RETURN",
                    details={
                        "item_id": str(item.id),
                        "returnable": str(item.received_quantity - item.returned_quantity),
                    },
                )
        settings = await get_company_settings(self.db, self.tenant_id)
        ledger = StockLedger(
            self.db,
            self.tenant_id,
            self.access.user_id,
            allow_negative=settings.allow_negative_stock,
        )
        await ledger.lock_products(i.product_id for i, _ in lines)
        balances = await ledger.lock_balances((po.warehouse_id, i.product_id) for i, _ in lines)
        doc = await self._document(po, "return", data.reason)
        for line_no, (item, quantity) in enumerate(lines, start=1):
            await ledger.move(
                balances[(po.warehouse_id, item.product_id)],
                movement_type="purchase_return",
                quantity=quantity,
                unit_cost=item.unit_cost,
                reference_type="purchase_return",
                reference_id=doc.id,
                line_no=line_no,
                reason=data.reason,
            )
            item.returned_quantity += quantity
            self.db.add(
                PurchaseReceiptItem(
                    tenant_id=self.tenant_id,
                    purchase_receipt_id=doc.id,
                    line_no=line_no,
                    purchase_order_item_id=item.id,
                    product_id=item.product_id,
                    quantity=quantity,
                    unit_cost=item.unit_cost,
                )
            )
        await self.db.flush()
        audit(
            self.db,
            self.access,
            "purchase.returned",
            "purchase_order",
            po.id,
            f"{po.number} / {doc.number}",
            {"reason": data.reason},
        )
        return await self.detail(po.id, po)

    async def pay(self, po_id: uuid.UUID, data: PaymentIn) -> PurchaseDetail:
        po = await self._load(po_id, lock=True)
        if po.status in ("draft", "cancelled"):
            raise ConflictError("This purchase cannot be paid", code="INVALID_STATUS")
        due = po.total - po.paid_amount
        if data.amount > due:
            raise ConflictError(
                "Payment exceeds the balance due", code="OVERPAYMENT", details={"due": str(due)}
            )
        self.db.add(
            Payment(
                tenant_id=self.tenant_id,
                direction="out",
                method=data.method,
                amount=money(data.amount),
                purchase_order_id=po.id,
                reference=data.reference,
                created_by=self.access.user_id,
            )
        )
        po.paid_amount += data.amount
        await self.db.flush()
        return await self.detail(po.id, po)
