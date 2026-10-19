"""Tiny JSON HTTP API (stdlib only): POST /invoice -> totals, GET /health."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .billing import LineItem, add_tax, apply_discount, invoice_total, subtotal


def compute(payload: dict) -> dict:
    items = [LineItem(i["description"], Decimal(str(i["unit_price"])), int(i.get("quantity", 1)))
             for i in payload.get("items", [])]
    disc = Decimal(str(payload.get("discount_percent", "0")))
    tax = Decimal(str(payload.get("tax_percent", "18")))
    sub = subtotal(items)
    after = apply_discount(sub, disc)
    return {
        "subtotal": str(sub),
        "after_discount": str(after),
        "total": str(invoice_total(items, disc, tax)),
        "tax": str(add_tax(after, tax) - after),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/invoice":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, compute(payload))
        except (ValueError, KeyError, InvalidOperation, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})

    def log_message(self, *args):  # keep test output clean
        pass


def serve(port: int = 8080) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
