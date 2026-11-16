import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.money import MoneyIn, QtyIn
from app.modules.purchasing.schemas import Method, Note, PaymentIn, PositiveMoney

__all__ = ["PaymentIn"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SaleItemIn(_Strict):
    product_id: uuid.UUID
    quantity: QtyIn
    # Optional override; defaults to the product's selling price. Totals are always
    # computed by the server – the client cannot send them.
    unit_price: MoneyIn | None = None
    discount_amount: MoneyIn = Decimal("0")


class SalePaymentIn(_Strict):
    method: Method = "cash"
    amount: PositiveMoney
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = (
        None
    )


class SaleCreate(_Strict):
    warehouse_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    items: Annotated[list[SaleItemIn], Field(min_length=1, max_length=200)]
    payments: Annotated[list[SalePaymentIn], Field(max_length=5)] = []
    notes: Note | None = None


class ReturnLineIn(_Strict):
    sale_item_id: uuid.UUID
    quantity: QtyIn


class SaleReturnCreate(_Strict):
    items: Annotated[list[ReturnLineIn], Field(min_length=1, max_length=200)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]

    @model_validator(mode="after")
    def _unique(self):
        if len({i.sale_item_id for i in self.items}) != len(self.items):
            raise ValueError("An item may appear only once")
        return self


class CancelRequest(_Strict):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class SaleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    line_no: int
    product_id: uuid.UUID
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal
    returned_quantity: Decimal


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    direction: str
    method: str
    amount: Decimal
    reference: str | None
    created_at: datetime


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    customer_id: uuid.UUID | None
    customer_name: str | None = None
    warehouse_id: uuid.UUID
    warehouse_name: str = ""
    status: str
    payment_status: str = "paid"
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    paid_amount: Decimal
    returned_amount: Decimal
    balance_due: Decimal = Decimal("0")
    notes: str | None
    created_at: datetime


class SaleDetail(SaleOut):
    items: list[SaleItemOut] = []
    payments: list[PaymentOut] = []
    cashier_name: str = ""
    change_due: Decimal = Decimal("0")
    refund_amount: Decimal = Decimal("0")
    idempotent_replay: bool = False
