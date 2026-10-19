"""Invoice arithmetic. Money is Decimal, rounded half-up to 2 places."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineItem:
    description: str
    unit_price: Decimal
    quantity: int = 1

    def total(self) -> Decimal:
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")
        return money(self.unit_price * self.quantity)


def subtotal(items: list[LineItem]) -> Decimal:
    return money(sum((i.total() for i in items), Decimal("0")))


def apply_discount(amount: Decimal, percent: Decimal) -> Decimal:
    if not Decimal("0") <= percent <= Decimal("100"):
        raise ValueError("discount percent must be between 0 and 100")
    return money(amount * (Decimal("100") - percent) / Decimal("100"))


def add_tax(amount: Decimal, rate_percent: Decimal) -> Decimal:
    if rate_percent < 0:
        raise ValueError("tax rate must be non-negative")
    return money(amount * (Decimal("100") + rate_percent) / Decimal("100"))


def invoice_total(items: list[LineItem], discount_percent=Decimal("0"),
                  tax_percent=Decimal("18")) -> Decimal:
    """Discount first, then tax (GST-style default of 18%)."""
    return add_tax(apply_discount(subtotal(items), Decimal(discount_percent)), Decimal(tax_percent))
