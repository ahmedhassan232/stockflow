import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.money import CostIn, MoneyIn, RateIn

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]
Barcode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=64, pattern=r"^[0-9A-Za-z-]+$"
    ),
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryCreate(_Strict):
    name: Name
    description: Text500 | None = None
    parent_id: uuid.UUID | None = None


class CategoryUpdate(_Strict):
    name: Name | None = None
    description: Text500 | None = None
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None


class CategoryOut(_Out):
    id: uuid.UUID
    name: str
    description: str | None
    parent_id: uuid.UUID | None
    is_active: bool


class UnitCreate(_Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    abbreviation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)
    ]


class UnitUpdate(_Strict):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None
    ) = None
    abbreviation: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)] | None
    ) = None
    is_active: bool | None = None


class UnitOut(_Out):
    id: uuid.UUID
    name: str
    abbreviation: str
    is_active: bool


class ProductCreate(_Strict):
    """`average_cost` is intentionally absent: only goods receipts can change it."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    sku: Sku
    barcode: Barcode | None = None
    category_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    description: Text500 | None = None
    purchase_price: CostIn = Decimal("0")
    selling_price: MoneyIn = Decimal("0")
    tax_rate: RateIn = Decimal("0")
    track_inventory: bool = True


class ProductUpdate(_Strict):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    barcode: Barcode | None = None
    category_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    description: Text500 | None = None
    purchase_price: CostIn | None = None
    selling_price: MoneyIn | None = None
    tax_rate: RateIn | None = None
    is_active: bool | None = None


class ProductOut(_Out):
    id: uuid.UUID
    name: str
    sku: str
    barcode: str | None
    category_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    description: str | None
    purchase_price: Decimal
    selling_price: Decimal
    average_cost: Decimal
    tax_rate: Decimal
    track_inventory: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WarehouseStock(BaseModel):
    warehouse_id: uuid.UUID
    warehouse_name: str
    quantity: Decimal
    minimum_stock_level: Decimal


class ProductDetail(ProductOut):
    total_stock: Decimal
    stock: list[WarehouseStock]
