"""Release notes + rollback plan from Conventional Commit subjects."""
from __future__ import annotations

import re

_CC = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<desc>.+)$")
SECTIONS = [
    ("breaking", "⚠️ Breaking changes"),
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
    ("security", "Security"),
    ("refactor", "Refactoring"),
    ("test", "Tests"),
    ("ci", "CI/CD"),
    ("docs", "Documentation"),
    ("other", "Other"),
]


def parse_commits(lines: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {k: [] for k, _ in SECTIONS}
    for raw in lines:
        line = raw.strip()
        if not line or line.lower().startswith("merge "):
            continue
        # Accept "sha subject" (git log --oneline) or bare subjects.
        parts = line.split(" ", 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{7,40}", parts[0]):
            line = parts[1]
        m = _CC.match(line)
        if not m:
            buckets["other"].append(line)
            continue
        desc = m.group("desc")
        if m.group("scope"):
            desc = f"**{m.group('scope')}:** {desc}"
        if m.group("bang") or "BREAKING CHANGE" in line:
            buckets["breaking"].append(desc)
        t = m.group("type")
        buckets[t if t in buckets else "other"].append(desc)
    return buckets


def render_release_notes(version: str, lines: list[str], risk_level: str | None = None) -> str:
    b = parse_commits(lines)
    out = [f"## {version}", ""]
    if risk_level:
        out += [f"Risk gate verdict for this release: **{risk_level}**", ""]
    for key, title in SECTIONS:
        if b[key]:
            out.append(f"### {title}")
            out += [f"- {d}" for d in b[key]]
            out.append("")
    out += render_rollback(version, risk_level)
    return "\n".join(out).rstrip() + "\n"


def render_rollback(version: str, risk_level: str | None) -> list[str]:
    steps = [
        "### Rollback plan",
        f"1. In **Deploy > Releases**, note the release before `{version}`.",
        "2. Re-run the `pages` job (production gate) from that tag's pipeline, or revert the merge commit and let the pipeline redeploy.",
        "3. Confirm the `post_deploy_probe` job is green.",
    ]
    if risk_level == "HIGH":
        steps.append("4. HIGH risk: keep the reverting MR open until the risk gate re-scores it below HIGH.")
    return steps
