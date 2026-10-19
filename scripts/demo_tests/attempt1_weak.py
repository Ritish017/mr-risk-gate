from decimal import Decimal

from tinyledger.billing import legacy_total, loyalty_discount


def test_loyalty_discount_runs():
    assert isinstance(loyalty_discount(Decimal("100.00"), 3), Decimal)


def test_legacy_total_runs():
    assert legacy_total(Decimal("100.00"), Decimal("18")) > 0
