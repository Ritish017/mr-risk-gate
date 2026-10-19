import json
import threading
import urllib.request
from decimal import Decimal
from http.server import ThreadingHTTPServer

import pytest

from tinyledger.billing import LineItem, add_tax, apply_discount, invoice_total, money, subtotal
from tinyledger.server import Handler, compute


def test_money_rounds_half_up():
    assert money("2.345") == Decimal("2.35") and money(1) == Decimal("1.00")


def test_invoice_total_discount_then_tax():
    items = [LineItem("plan", Decimal("100.00"), 2)]
    assert subtotal(items) == Decimal("200.00")
    assert invoice_total(items, Decimal("10"), Decimal("18")) == Decimal("212.40")


@pytest.mark.parametrize("pct", [Decimal("-1"), Decimal("100.01")])
def test_discount_bounds(pct):
    with pytest.raises(ValueError):
        apply_discount(Decimal("10"), pct)


def test_negative_tax_and_quantity_rejected():
    with pytest.raises(ValueError):
        add_tax(Decimal("10"), Decimal("-5"))
    with pytest.raises(ValueError):
        LineItem("x", Decimal("1"), -1).total()


def test_compute_payload():
    out = compute({"items": [{"description": "a", "unit_price": "19.99", "quantity": 3}], "discount_percent": "0"})
    assert out == {"subtotal": "59.97", "after_discount": "59.97", "total": "70.76", "tax": "10.79"}


def test_http_server_end_to_end():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    # bypass any HTTP(S)_PROXY in the environment for loopback
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    urllib.request.install_opener(opener)
    try:
        assert json.load(urllib.request.urlopen(base + "/health")) == {"status": "ok"}
        req = urllib.request.Request(base + "/invoice", method="POST",
                                     data=json.dumps({"items": [{"description": "p", "unit_price": "100", "quantity": 2}],
                                                      "discount_percent": "10"}).encode())
        assert json.load(urllib.request.urlopen(req))["total"] == "212.40"
        bad = urllib.request.Request(base + "/invoice", method="POST", data=b'{"items": [{"unit_price": "x"}]}')
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad)
        assert e.value.code == 400
    finally:
        urllib.request.install_opener(None)
        srv.shutdown()
