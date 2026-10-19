"""Static "risk ledger" site for GitLab Pages (release + monitor surface)."""
from __future__ import annotations

import html
import json
from pathlib import Path

_CSS = """
:root{--ink:#171321;--muted:#626168;--line:#ececef;--bg:#f7f6fa;--low:#108548;--med:#ab6100;--high:#dd2b0e;--accent:#7759c2}
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{background:var(--ink);color:#fff;padding:28px 40px 24px}header h1{margin:0;font-size:24px;letter-spacing:-.01em}
header p{margin:6px 0 0;opacity:.75;font-size:14px}main{padding:24px 40px;max-width:1120px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card b{display:block;font-size:28px;line-height:1.1}.card span{color:var(--muted);font-size:13px}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;font-size:14px;vertical-align:middle}
th{background:#f3f2f7;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-weight:700;font-size:12px;color:#fff}
.LOW{color:var(--low);font-weight:700}.MEDIUM{color:var(--med);font-weight:700}.HIGH{color:var(--high);font-weight:700}
.pill.LOW{background:var(--low);color:#fff}.pill.MEDIUM{background:var(--med);color:#fff}.pill.HIGH{background:var(--high);color:#fff}
td:nth-child(3){white-space:nowrap}.bar{width:110px;height:8px;background:#eee;border-radius:4px;display:inline-block;vertical-align:middle;margin-right:8px}
.bar i{display:block;height:8px;border-radius:4px}
.proof{font-weight:700}.PROVEN{color:var(--low)}.WEAK{color:var(--high)}.NO_MUTANTS,.none{color:var(--muted);font-weight:400}
.BASELINE_FAILED{color:var(--high)}
code{background:#f3f2f7;padding:1px 4px;border-radius:3px}footer{padding:16px 40px 32px;color:var(--muted);font-size:13px}
@media(max-width:760px){.cards{grid-template-columns:repeat(2,1fr)}main,header,footer{padding-left:16px;padding-right:16px}}
"""

_LEVEL_COLOR = {"LOW": "#108548", "MEDIUM": "#ab6100", "HIGH": "#dd2b0e"}


def _proof_cell(m: dict | None) -> str:
    if not m:
        return "<span class='proof none'>not run</span>"
    v = m.get("verdict", "?")
    if v in ("PROVEN", "WEAK") and m.get("total"):
        return (f"<span class='proof {v}'>{v}</span> "
                f"<span class='none'>{m.get('killed', 0)}/{m.get('total', 0)} planted bugs caught</span>")
    label = {"NO_MUTANTS": "no logic changed", "BASELINE_FAILED": "tests failing"}.get(v, v)
    return f"<span class='proof {html.escape(v)}'>{html.escape(label)}</span>"


def build_ledger(entries: list[dict], out_dir: Path, title: str = "MR Risk Gate — risk ledger") -> Path:
    """entries: [{"ref": str, "report": risk-report-dict, "url": optional str, "mutation": optional dict}]"""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    proven = proof_runs = 0
    for e in entries:
        r = e["report"]
        counts[r["level"]] = counts.get(r["level"], 0) + 1
        m = e.get("mutation")
        if m and m.get("verdict") in ("PROVEN", "WEAK"):
            proof_runs += 1
            proven += m["verdict"] == "PROVEN"
        top = r["findings"][0]["reason"] if r.get("findings") else "no signals"
        ref = html.escape(e.get("ref", "?"))
        if e.get("url"):
            ref = f'<a href="{html.escape(e["url"])}">{ref}</a>'
        score = max(0, min(100, int(r.get("score", 0))))
        bar = (f"<span class='bar'><i style='width:{score}%;background:{_LEVEL_COLOR.get(r['level'], '#888')}'></i></span>"
               f"{score}")
        rows.append(
            f"<tr><td>{ref}</td><td><span class='pill {r['level']}'>{r['level']}</span>"
            f"</td><td>{bar}</td>"
            f"<td>{r['files_changed']}</td><td>+{r['lines_added']}/-{r['lines_removed']}</td>"
            f"<td>{_proof_cell(m)}</td><td>{html.escape(top)}</td></tr>"
        )
    body = "\n".join(rows) or "<tr><td colspan=7>No scored changes yet.</td></tr>"
    skipped = counts.get("LOW", 0)
    cards = (
        f"<div class='cards'><div class='card'><b>{len(entries)}</b><span>changes scored</span></div>"
        f"<div class='card'><b class='HIGH'>{counts.get('HIGH', 0)}</b><span>HIGH · <b class='MEDIUM' style='display:inline;font-size:inherit'>{counts.get('MEDIUM', 0)}</b> MEDIUM</span></div>"
        f"<div class='card'><b class='LOW'>{skipped}</b><span>LOW: no test-writing agent run</span></div>"
        f"<div class='card'><b>{proven}/{proof_runs}</b><span>risky changes with tests proven by mutation</span></div></div>"
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>{_CSS}</style></head><body>
<header><h1>{html.escape(title)}</h1><p>Every change, its deterministic risk score, why, and whether its tests were proven to catch bugs.</p></header>
<main>{cards}<table><thead><tr><th>Change</th><th>Level</th><th>Score</th><th>Files</th><th>Lines</th><th>Test proof</th><th>Top reason</th></tr></thead>
<tbody>
{body}
</tbody></table></main>
<footer>Generated by <code>riskgate ledger</code> from CI artifacts. Health: <a href="health.json">health.json</a> · data: <a href="ledger.json">ledger.json</a></footer>
</body></html>"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "health.json").write_text(json.dumps({"status": "ok", "entries": len(entries)}), encoding="utf-8")
    (out_dir / "ledger.json").write_text(json.dumps(entries, indent=1), encoding="utf-8")
    return out_dir / "index.html"


def load_history(url_or_path: str | None, fetch=None) -> list[dict]:
    """Best effort: previous ledger.json from the live Pages site or a file. Never raises."""
    if not url_or_path:
        return []
    try:
        if url_or_path.startswith(("http://", "https://")):
            import urllib.request
            fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=10).read().decode("utf-8"))
            data = json.loads(fetch(url_or_path))
        else:
            data = json.loads(Path(url_or_path).read_text(encoding="utf-8"))
        return [e for e in data if isinstance(e, dict) and "report" in e]
    except Exception:
        return []


def merge_entries(history: list[dict], new: list[dict], limit: int = 200) -> list[dict]:
    """Newest first, de-duplicated by ref."""
    seen, out = set(), []
    for e in new + history:
        if e.get("ref") in seen:
            continue
        seen.add(e.get("ref"))
        out.append(e)
    return out[:limit]
