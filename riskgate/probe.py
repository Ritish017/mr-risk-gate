"""Post-deploy probe (monitor stage): status, latency and an expected body marker."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass


@dataclass
class ProbeResult:
    url: str
    ok: bool
    status: int | None
    latency_ms: int
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def probe(url: str, expect_status: int = 200, expect_text: str | None = None,
          max_latency_ms: int = 3000, timeout: float = 10.0, retries: int = 3,
          backoff_s: float = 2.0, opener=urllib.request.urlopen) -> ProbeResult:
    last = ProbeResult(url, False, None, 0, "not attempted")
    for attempt in range(retries):
        start = time.monotonic()
        try:
            with opener(url, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
        except Exception as e:  # network error: retry
            last = ProbeResult(url, False, None, int((time.monotonic() - start) * 1000), f"error: {e}")
            if attempt + 1 < retries:
                time.sleep(backoff_s)
            continue
        latency = int((time.monotonic() - start) * 1000)
        if status != expect_status:
            last = ProbeResult(url, False, status, latency, f"expected HTTP {expect_status}")
        elif expect_text and expect_text not in body:
            last = ProbeResult(url, False, status, latency, f"marker {expect_text!r} not in body")
        elif latency > max_latency_ms:
            last = ProbeResult(url, False, status, latency, f"latency {latency}ms > {max_latency_ms}ms")
        else:
            return ProbeResult(url, True, status, latency, "healthy")
        if attempt + 1 < retries:
            time.sleep(backoff_s)
    return last
