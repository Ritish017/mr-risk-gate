import io
import json
import urllib.error

from riskgate.ledger import build_ledger, load_history, merge_entries
from riskgate.probe import probe

REPORT = {"level": "HIGH", "score": 80, "files_changed": 3, "lines_added": 10, "lines_removed": 2,
          "findings": [{"reason": "touches money <calc>", "points": 25}]}


def test_ledger_writes_html_health_and_escapes(tmp_path):
    out = build_ledger([{"ref": "abc123", "report": REPORT}], tmp_path / "public")
    html = out.read_text()
    assert "class='pill HIGH'" in html and "abc123" in html and "&lt;calc&gt;" in html
    assert json.loads((tmp_path / "public" / "health.json").read_text())["status"] == "ok"
    assert json.loads((tmp_path / "public" / "ledger.json").read_text())[0]["ref"] == "abc123"


def test_history_merge_dedupes_newest_first(tmp_path):
    hist = tmp_path / "ledger.json"
    hist.write_text(json.dumps([{"ref": "old", "report": REPORT}, {"ref": "same", "report": REPORT}]))
    merged = merge_entries(load_history(str(hist)), [{"ref": "same", "report": {**REPORT, "score": 1}}])
    assert [e["ref"] for e in merged] == ["same", "old"] and merged[0]["report"]["score"] == 1


def test_history_never_raises():
    assert load_history("https://example.invalid/ledger.json", fetch=lambda u: (_ for _ in ()).throw(OSError())) == []
    assert load_history(None) == []
    assert load_history("/nonexistent/ledger.json") == []


class FakeResp(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body.encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_probe_healthy_and_marker():
    r = probe("http://x", expect_text='"ok"', opener=lambda u, timeout: FakeResp('{"status": "ok"}'))
    assert r.ok and r.status == 200 and r.reason == "healthy"


def test_probe_retries_then_fails_on_marker():
    calls = []

    def opener(u, timeout):
        calls.append(u)
        return FakeResp("nope")

    r = probe("http://x", expect_text="ok!", retries=3, backoff_s=0, opener=opener)
    assert not r.ok and len(calls) == 3 and "marker" in r.reason


def test_probe_http_error_and_network_error():
    def http_err(u, timeout):
        raise urllib.error.HTTPError(u, 503, "down", {}, None)

    r = probe("http://x", retries=1, opener=http_err)
    assert not r.ok and r.status == 503

    def net_err(u, timeout):
        raise OSError("connection refused")

    r = probe("http://x", retries=2, backoff_s=0, opener=net_err)
    assert not r.ok and r.status is None and "connection refused" in r.reason


def test_ledger_shows_test_proof_and_summary_cards(tmp_path):
    low = {**REPORT, "level": "LOW", "score": 0, "findings": []}
    entries = [{"ref": "feat/x", "report": REPORT,
                "mutation": {"verdict": "PROVEN", "killed": 9, "total": 9}},
               {"ref": "docs/y", "report": low}]
    page = build_ledger(entries, tmp_path / "p").read_text()
    assert "9/9 planted bugs caught" in page and "PROVEN" in page
    assert "LOW: no test-writing agent run" in page and "1/1" in page
    assert "not run" in page  # docs change has no proof
