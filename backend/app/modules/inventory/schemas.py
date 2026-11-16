import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.money import QtyIn

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdjustmentCreate(_Strict):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    direction: Literal["in", "out"]
    quantity: QtyIn
    reason: Reason
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = (
        None
    )


class AdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    direction: str
    quantity: Decimal
    reason: str
    reference: str | None
    created_by: uuid.UUID
    created_at: datetime
    balance_after: Decimal | None = None
    idempotent_replay: bool = False


class TransferItemIn(_Strict):
    product_id: uuid.UUID
    quantity: QtyIn


class TransferCreate(_Strict):
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    items: Annotated[list[TransferItemIn], Field(min_length=1, max_length=200)]
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None

    @model_validator(mode="after")
    def _check(self) -> "TransferCreate":
        if self.from_warehouse_id == self.to_warehouse_id:
            raise ValueError("Source and destination warehouses must be different")
        ids = [i.product_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once in a transfer")
        return self


class TransferItemOut(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal


class TransferOut(BaseModel):
    id: uuid.UUID
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    notes: str | None
    created_by: uuid.UUID
    created_at: datetime
    items: list[TransferItemOut]
    idempotent_replay: bool = False


class MinimumLevelSet(_Strict):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    minimum_stock_level: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]


class BalanceOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    sku: str
    warehouse_id: uuid.UUID
    warehouse_name: str
    quantity: Decimal
    minimum_stock_level: Decimal
    is_low: bool
    average_cost: Decimal
    stock_value: Decimal


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: str
    quantity_in: Decimal
    quantity_out: Decimal
    unit_cost: Decimal
    balance_after: Decimal
    reference_type: str
    reference_id: uuid.UUID
    reason: str | None
    created_by: uuid.UUID
    created_at: datetime


class WarehouseValuation(BaseModel):
    warehouse_id: uuid.UUID
    warehouse_name: str
    total_quantity: Decimal
    stock_value: Decimal


class ValuationOut(BaseModel):
    method: str = "weighted_average"
    total_value: Decimal
    warehouses: list[WarehouseValuation]
