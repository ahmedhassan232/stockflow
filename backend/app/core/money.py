"""Decimal helpers. Money, cost and quantity are NEVER floats anywhere in the system."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import Field
from sqlalchemy import Numeric

MONEY = Numeric(14, 2)  # invoice amounts
COST = Numeric(14, 4)  # unit costs / average cost (extra precision avoids drift)
QTY = Numeric(14, 3)  # quantities (supports kg, m, …)
RATE = Numeric(5, 2)  # percentages

ZERO = Decimal("0")
_CENT, _COST, _QTY = Decimal("0.01"), Decimal("0.0001"), Decimal("0.001")


def money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def cost(value: Decimal) -> Decimal:
    return value.quantize(_COST, rounding=ROUND_HALF_UP)


def qty(value: Decimal) -> Decimal:
    return value.quantize(_QTY, rounding=ROUND_HALF_UP)


# Request field types (validated on input; totals are always recomputed by the backend).
MoneyIn = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
CostIn = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
QtyIn = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
RateIn = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
