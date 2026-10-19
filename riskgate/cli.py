"""riskgate command line. Used by CI jobs and by Duo flow agents via run_command.

Diff sources (first match wins): --diff FILE, --base SHA [--head SHA] (git diff
in the current repo), or stdin.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .diffparse import parse_unified_diff
from .evidence import build_evidence
from .ledger import build_ledger, load_history, merge_entries
from .notes import render_release_notes
from .policy import load_policy
from .probe import probe
from .score import render_markdown, score_changes
from .testgaps import find_gaps, to_dicts, untested
from . import mutate as _mutate


def _read_diff(args) -> str:
    if getattr(args, "diff", None):
        return Path(args.diff).read_text(encoding="utf-8", errors="replace")
    if getattr(args, "base", None):
        head = args.head or "HEAD"
        return subprocess.run(
            ["git", "diff", "--no-color", "--unified=3", f"{args.base}...{head}"],
            check=True, capture_output=True, text=True,
        ).stdout
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("riskgate: provide --diff FILE, --base SHA, or a diff on stdin")


def _add_diff_args(p):
    p.add_argument("--diff", help="unified diff file")
    p.add_argument("--base", help="base commit/ref (uses git diff base...head)")
    p.add_argument("--head", help="head commit/ref (default HEAD)")


def cmd_score(args) -> int:
    files = parse_unified_diff(_read_diff(args))
    report = score_changes(files, load_policy(args.policy))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(render_markdown(report), encoding="utf-8")
    if args.dotenv_out:
        Path(args.dotenv_out).write_text(f"RISK_LEVEL={report.level}\nRISK_SCORE={report.score}\n")
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    elif args.format == "level":
        print(report.level)
    else:
        print(render_markdown(report))
    if args.fail_on and ["LOW", "MEDIUM", "HIGH"].index(report.level) >= ["LOW", "MEDIUM", "HIGH"].index(args.fail_on):
        return 2
    return 0


def cmd_testgaps(args) -> int:
    files = parse_unified_diff(_read_diff(args))
    gaps = find_gaps(files, root=args.root, test_dirs=args.test_dir or ["tests"])
    todo = untested(gaps)
    if args.format == "json":
        print(json.dumps({"changed_functions": to_dicts(gaps), "untested": to_dicts(todo)}, indent=2))
    else:
        if not todo:
            print("No untested changed functions.")
        for g in todo:
            print(f"{g.path}:{g.lineno} {g.qualname} ({g.changed_lines} changed lines, no test reference)")
    return 0


def cmd_mutate(args) -> int:
    import shlex
    files = parse_unified_diff(_read_diff(args))
    pol = load_policy(args.policy).get("mutation", {})
    report = _mutate.run_mutation(
        files, root=args.root,
        test_cmd=shlex.split(args.test_cmd) if args.test_cmd else None,
        test_dirs=args.test_dir or ["tests"],
        max_mutants=args.max_mutants or pol.get("max_mutants", 40),
        timeout_s=args.timeout or pol.get("timeout_s", 60),
        min_kill_ratio=args.min_kill_ratio if args.min_kill_ratio is not None else pol.get("min_kill_ratio", 0.8),
    )
    md = _mutate.render_markdown(report)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    elif args.format == "verdict":
        print(report.verdict)
    else:
        print(md)
    if args.fail_on_weak and report.verdict in ("WEAK", "BASELINE_FAILED"):
        return 3
    return 0


def cmd_notes(args) -> int:
    if args.commits:
        lines = Path(args.commits).read_text(encoding="utf-8").splitlines()
    else:
        lines = sys.stdin.read().splitlines()
    print(render_release_notes(args.version, lines, args.risk_level))
    return 0


def cmd_evidence(args) -> int:
    md = build_evidence(Path(args.risk), Path(args.junit), [Path(p) for p in args.security or []],
                        mutation_json=Path(args.mutation) if args.mutation else None)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    print(md)
    return 0


def cmd_ledger(args) -> int:
    entries = []
    for spec in args.report:
        ref, _, path = spec.partition("=")
        if not path:
            ref, path = Path(spec).stem, spec
        p = Path(path)
        if p.exists():
            entries.append({"ref": ref, "report": json.loads(p.read_text(encoding="utf-8"))})
    for spec in args.mutation:
        ref, _, path = spec.partition("=")
        mp = Path(path)
        if mp.exists():
            for e in entries:
                if e["ref"] == ref:
                    e["mutation"] = json.loads(mp.read_text(encoding="utf-8"))
    entries = merge_entries(load_history(args.history), entries)
    out = build_ledger(entries, Path(args.out))
    print(out)
    return 0


def cmd_probe(args) -> int:
    r = probe(args.url, args.expect_status, args.expect_text, args.max_latency_ms,
              retries=args.retries, backoff_s=args.backoff)
    print(json.dumps(r.to_dict(), indent=2))
    return 0 if r.ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="riskgate", description=__doc__)
    ap.add_argument("--version", action="version", version=f"riskgate {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="score a diff")
    _add_diff_args(s)
    s.add_argument("--policy", help="policy JSON (default ./riskgate.json)")
    s.add_argument("--format", choices=["md", "json", "level"], default="md")
    s.add_argument("--json-out")
    s.add_argument("--md-out")
    s.add_argument("--dotenv-out", help="write RISK_LEVEL/RISK_SCORE for artifacts:reports:dotenv")
    s.add_argument("--fail-on", choices=["MEDIUM", "HIGH"])
    s.set_defaults(func=cmd_score)

    t = sub.add_parser("testgaps", help="changed functions with no test references")
    _add_diff_args(t)
    t.add_argument("--root", default=".")
    t.add_argument("--test-dir", action="append")
    t.add_argument("--format", choices=["text", "json"], default="text")
    t.set_defaults(func=cmd_testgaps)

    m = sub.add_parser("mutate", help="prove the tests catch bugs planted on the changed lines")
    _add_diff_args(m)
    m.add_argument("--policy", help="policy JSON (default ./riskgate.json)")
    m.add_argument("--root", default=".")
    m.add_argument("--test-dir", action="append")
    m.add_argument("--test-cmd", help="test command (default: python -m pytest -q -x)")
    m.add_argument("--max-mutants", type=int)
    m.add_argument("--timeout", type=int, help="seconds per test run")
    m.add_argument("--min-kill-ratio", type=float)
    m.add_argument("--format", choices=["md", "json", "verdict"], default="md")
    m.add_argument("--json-out")
    m.add_argument("--md-out")
    m.add_argument("--fail-on-weak", action="store_true", help="exit 3 when verdict is WEAK/BASELINE_FAILED")
    m.set_defaults(func=cmd_mutate)

    n = sub.add_parser("notes", help="release notes + rollback plan from commit subjects")
    n.add_argument("--version", required=True)
    n.add_argument("--commits", help="file with one commit subject per line (default stdin)")
    n.add_argument("--risk-level")
    n.set_defaults(func=cmd_notes)

    e = sub.add_parser("evidence", help="compliance evidence bundle")
    e.add_argument("--risk", default="risk.json")
    e.add_argument("--junit", default="junit.xml")
    e.add_argument("--security", action="append")
    e.add_argument("--mutation", help="mutation.json from riskgate mutate")
    e.add_argument("--out")
    e.set_defaults(func=cmd_evidence)

    l = sub.add_parser("ledger", help="static risk ledger site")
    l.add_argument("--report", action="append", default=[], help="REF=path/to/risk.json")
    l.add_argument("--mutation", action="append", default=[], help="REF=path/to/mutation.json")
    l.add_argument("--out", default="public")
    l.add_argument("--history", help="previous ledger.json URL or path (best effort)")
    l.set_defaults(func=cmd_ledger)

    p = sub.add_parser("probe", help="post-deploy health probe")
    p.add_argument("url")
    p.add_argument("--expect-status", type=int, default=200)
    p.add_argument("--expect-text")
    p.add_argument("--max-latency-ms", type=int, default=3000)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--backoff", type=float, default=2.0, help="seconds between attempts")
    p.set_defaults(func=cmd_probe)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
