from decimal import Decimal

import pytest

from tinyledger.billing import legacy_total, loyalty_discount


def test_loyalty_discount_one_percent_per_year():
    assert loyalty_discount(Decimal("100.00"), 3) == Decimal("97.00")


def test_loyalty_discount_capped_at_fifteen_percent():
    assert loyalty_discount(Decimal("100.00"), 15) == Decimal("85.00")
    assert loyalty_discount(Decimal("100.00"), 40) == Decimal("85.00")


def test_loyalty_discount_zero_years_is_full_price():
    assert loyalty_discount(Decimal("59.99"), 0) == Decimal("59.99")


def test_legacy_total_adds_tax():
    assert legacy_total(Decimal("100.00"), Decimal("18")) == pytest.approx(118.0)
    assert legacy_total(Decimal("50.00"), Decimal("0")) == pytest.approx(50.0)
