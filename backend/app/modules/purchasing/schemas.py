import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.money import CostIn, QtyIn, RateIn

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Method = Literal["cash", "card", "bank_transfer", "wallet"]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PurchaseItemIn(_Strict):
    product_id: uuid.UUID
    quantity: QtyIn
    unit_cost: CostIn
    tax_rate: RateIn = Decimal("0")


class PurchaseCreate(_Strict):
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID
    items: Annotated[list[PurchaseItemIn], Field(min_length=1, max_length=200)]
    notes: Note | None = None
    status: Literal["draft", "ordered"] = "ordered"

    @model_validator(mode="after")
    def _unique_products(self):
        ids = [i.product_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("A product may appear only once per purchase order")
        return self


class DocLineIn(_Strict):
    item_id: uuid.UUID
    quantity: QtyIn


class ReceiveRequest(_Strict):
    """Omit `items` to receive everything that is still outstanding."""

    items: Annotated[list[DocLineIn], Field(min_length=1, max_length=200)] | None = None
    notes: Note | None = None

    @model_validator(mode="after")
    def _unique(self):
        if self.items and len({i.item_id for i in self.items}) != len(self.items):
            raise ValueError("An item may appear only once")
        return self


class PurchaseReturnRequest(_Strict):
    items: Annotated[list[DocLineIn], Field(min_length=1, max_length=200)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]

    @model_validator(mode="after")
    def _unique(self):
        if len({i.item_id for i in self.items}) != len(self.items):
            raise ValueError("An item may appear only once")
        return self


class PaymentIn(_Strict):
    amount: PositiveMoney
    method: Method = "cash"
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = (
        None
    )


class PurchaseItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    line_no: int
    product_id: uuid.UUID
    product_name: str = ""
    sku: str = ""
    quantity: Decimal
    unit_cost: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal
    received_quantity: Decimal
    returned_quantity: Decimal


class PurchaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    supplier_id: uuid.UUID
    supplier_name: str = ""
    warehouse_id: uuid.UUID
    warehouse_name: str = ""
    status: str
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    paid_amount: Decimal
    balance_due: Decimal = Decimal("0")
    notes: str | None
    created_at: datetime


class PurchaseDetail(PurchaseOut):
    items: list[PurchaseItemOut] = []
    idempotent_replay: bool = False
