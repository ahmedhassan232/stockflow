"""Authoritative document arithmetic (Decimal only). Prices are tax-exclusive; tax is
computed per line on the discounted amount and rounded half-up to 2 places, so the
invoice total always equals the sum of its printed lines."""

from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import AppError
from app.core.money import money

HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class LineAmounts:
    gross: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal

    @property
    def net(self) -> Decimal:
        return self.gross - self.discount


def line_amounts(
    quantity: Decimal, unit_price: Decimal, tax_rate: Decimal, discount: Decimal = Decimal("0")
) -> LineAmounts:
    gross = money(quantity * unit_price)
    discount = money(discount)
    if discount > gross:
        raise AppError("Discount cannot exceed the line amount", code="DISCOUNT_TOO_LARGE")
    tax = money((gross - discount) * tax_rate / HUNDRED)
    return LineAmounts(gross=gross, discount=discount, tax=tax, total=gross - discount + tax)


def proportion(amount: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    return money(amount * part / whole)
