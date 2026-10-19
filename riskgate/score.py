"""Explainable, deterministic MR risk scoring.

Every point added to the score carries a human-readable reason so the agent
(and the reviewer) can see *why* a change is risky. No ML, no network.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass, field

from .diffparse import FileChange


@dataclass
class Finding:
    rule: str
    points: int
    reason: str
    path: str | None = None
    line: int | None = None
    severity: str = "info"


@dataclass
class RiskReport:
    score: int
    level: str
    findings: list[Finding] = field(default_factory=list)
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    untested_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


def _match(path: str, globs: list[str]) -> bool:
    for g in globs:
        if fnmatch.fnmatch(path, g):
            return True
        # fnmatch's "**/" needs at least one dir; also try the root-level form.
        if g.startswith("**/") and fnmatch.fnmatch(path, g[3:]):
            return True
    return False


def score_changes(files: list[FileChange], policy: dict) -> RiskReport:
    findings: list[Finding] = []
    added = sum(len(f.added) for f in files)
    removed = sum(len(f.removed) for f in files)
    test_globs = policy["test_globs"]
    source_globs = policy["source_globs"]

    # 1. Size
    size_cfg = policy["size"]
    churn = added + removed
    size_pts = min(size_cfg["max_points"], (churn * size_cfg["points_per_100_lines"]) // 100)
    if size_pts:
        findings.append(Finding("size", size_pts, f"{churn} lines changed", severity="low"))

    # 2. Sensitive paths (each rule counted once per MR, listing first matching file)
    for rule in policy["sensitive_paths"]:
        hits = [f.path for f in files if _match(f.path, [rule["glob"]])]
        if hits:
            findings.append(Finding(
                "sensitive-path", rule["points"],
                f"touches {rule['reason']} ({', '.join(sorted(set(hits)))})",
                path=hits[0], severity="medium",
            ))

    # 3. Source changed without any test change
    tests_touched = [f for f in files if _match(f.path, test_globs) and f.status != "deleted"]
    sources = [f for f in files
               if f.path.endswith(".py") and _match(f.path, source_globs)
               and not _match(f.path, test_globs) and f.status != "deleted" and f.added]
    untested: list[str] = []
    if sources and not tests_touched:
        untested = sorted(f.path for f in sources)
        findings.append(Finding(
            "no-test-change", policy["untested_source_points"],
            f"source changed with no test changes: {', '.join(untested)}", severity="medium",
        ))

    # 4. Deleted tests / removed assertions
    for f in files:
        if _match(f.path, test_globs):
            removed_asserts = sum(1 for l in f.removed if l.strip().startswith("assert"))
            added_asserts = sum(1 for l in f.added if l.strip().startswith("assert"))
            if f.status == "deleted" or removed_asserts > added_asserts:
                findings.append(Finding(
                    "weakened-tests", policy["deleted_test_points"],
                    f"tests deleted or assertions removed in {f.path}", path=f.path, severity="high",
                ))

    # 5. Smells in added lines (secrets, dangerous calls)
    compiled = [(s, re.compile(s["regex"])) for s in policy["smells"]]
    seen: set[tuple[str, str]] = set()
    for f in files:
        if f.binary:
            continue
        is_policy_file = f.path in ("riskgate.json", "riskgate/policy.py")
        for text, lineno in zip(f.added, f.added_line_numbers):
            for smell, rx in compiled:
                if is_policy_file:
                    continue  # the policy legitimately contains the patterns
                if rx.search(text) and (smell["id"], f.path) not in seen:
                    seen.add((smell["id"], f.path))
                    findings.append(Finding(
                        smell["id"], smell["points"], f"{smell['id']} in added line",
                        path=f.path, line=lineno, severity=smell["severity"],
                    ))

    score = min(100, sum(x.points for x in findings))
    th = policy["thresholds"]
    critical = any(x.severity == "critical" for x in findings)
    level = "HIGH" if critical or score >= th["high"] else "MEDIUM" if score >= th["medium"] else "LOW"
    findings.sort(key=lambda x: -x.points)
    return RiskReport(score=score, level=level, findings=findings, files_changed=len(files),
                      lines_added=added, lines_removed=removed, untested_sources=untested)


def render_markdown(report: RiskReport) -> str:
    badge = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}[report.level]
    out = [
        f"### {badge} MR Risk Gate: **{report.level}** ({report.score}/100)",
        "",
        f"{report.files_changed} files · +{report.lines_added} / -{report.lines_removed} lines",
        "",
    ]
    if report.findings:
        out += ["| Points | Rule | Why | Where |", "|---:|---|---|---|"]
        for f in report.findings:
            where = f"`{f.path}`" + (f":{f.line}" if f.line else "") if f.path else ""
            out.append(f"| {f.points} | `{f.rule}` | {f.reason} | {where} |")
    else:
        out.append("No risk signals found.")
    out += ["", "_Scored deterministically by `riskgate` against `riskgate.json`._"]
    return "\n".join(out)
