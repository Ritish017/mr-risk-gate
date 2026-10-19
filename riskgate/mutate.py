"""Diff-scoped mutation testing: prove that the tests guarding a risky change
would actually catch a bug in it.

A passing test suite says nothing about whether the *changed* lines are
checked. An agent (or a hurried human) can write a test that calls the new
function and asserts almost nothing. `riskgate mutate` plants small, realistic
bugs only on the lines the merge request added (flip `<` to `<=`, `min` to
`max`, `+` to `-`, nudge a numeric literal, return None ...), runs the tests
against each mutant in a scratch copy of the repo, and reports which bugs the
tests caught ("killed") and which slipped through ("survived").

Deterministic, standard library only, never touches the working tree.
"""
from __future__ import annotations

import ast
import copy
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .diffparse import FileChange

_BINOP_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
               ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}
_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
             ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
             ast.Is: ast.IsNot, ast.IsNot: ast.Is}
_BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}
_CALL_SWAP = {"min": "max", "max": "min", "any": "all", "all": "any"}
_SKIP_DIRS = {".git", ".cache", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", "public", "results", "dist"}


@dataclass
class Mutant:
    id: str
    path: str
    line: int
    operator: str
    original: str
    mutated: str
    status: str = "pending"  # killed | survived | timeout | error
    seconds: float = 0.0


@dataclass
class MutationReport:
    verdict: str  # PROVEN | WEAK | NO_MUTANTS | BASELINE_FAILED
    killed: int = 0
    survived: int = 0
    total: int = 0
    kill_ratio: float | None = None
    min_kill_ratio: float = 0.8
    mutants: list[Mutant] = field(default_factory=list)
    baseline_ok: bool = True
    test_command: str = ""
    seconds: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mutants"] = [asdict(m) for m in self.mutants]
        return d


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return type(node).__name__


def _numeric_str(s: str) -> Decimal | None:
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _candidate_sites(tree: ast.AST, changed: set[int]):
    """Yield (node, operator_name, apply_fn) for every mutation site on a changed line.

    apply_fn(node_copy) mutates the copied node in place and returns a short
    description of the new code.
    """
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if line is None or line not in changed:
            continue
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAP:
            new = _BINOP_SWAP[type(node.op)]

            def fn(n, new=new):
                n.op = new()
            yield node, f"binop {type(node.op).__name__}->{new.__name__}", fn
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP_SWAP:
            new = _CMP_SWAP[type(node.ops[0])]

            def fn(n, new=new):
                n.ops = [new()]
            yield node, f"compare {type(node.ops[0]).__name__}->{new.__name__}", fn
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL_SWAP:
            new = _BOOL_SWAP[type(node.op)]

            def fn(n, new=new):
                n.op = new()
            yield node, f"boolop {type(node.op).__name__}->{new.__name__}", fn
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CALL_SWAP:
            new = _CALL_SWAP[node.func.id]

            def fn(n, new=new):
                n.func = ast.Name(id=new, ctx=ast.Load())
            yield node, f"call {node.func.id}->{new}", fn
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            def fn(n):
                n.op = ast.UAdd()  # replaced below by the operand itself
            yield node, "drop not", fn
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float) and not isinstance(node.value, bool):
            def fn(n):
                n.value = n.value + 1
            yield node, "number +1", fn
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _numeric_str(node.value) is not None \
                and len(node.value) <= 12:
            def fn(n):
                n.value = str(_numeric_str(n.value) + 1)
            yield node, "numeric string +1", fn
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            def fn(n):
                n.value = ast.Constant(value=None)
            yield node, "return None", fn


class _Replace(ast.NodeTransformer):
    """Replace the node at a given walk index with a mutated copy."""

    def __init__(self, target_index: int, apply_fn):
        self.target_index = target_index
        self.apply_fn = apply_fn
        self.idx = -1
        self.before = self.after = ""

    def generic_visit(self, node):
        return super().generic_visit(node)

    def visit(self, node):
        self.idx += 1
        if self.idx == self.target_index:
            self.before = _src(node)
            new = copy.deepcopy(node)
            self.apply_fn(new)
            if isinstance(new, ast.UnaryOp) and isinstance(new.op, ast.UAdd) and isinstance(node.op, ast.Not):
                new = new.operand
            self.after = _src(new)
            return new
        return self.generic_visit(node)


def _walk_index(tree: ast.AST, target: ast.AST) -> int:
    """Index of `target` in the same pre-order the NodeTransformer uses."""
    counter = [-1]
    found = [-1]

    def rec(n):
        counter[0] += 1
        if n is target:
            found[0] = counter[0]
            return True
        for _f, value in ast.iter_fields(n):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST) and rec(item):
                        return True
            elif isinstance(value, ast.AST) and rec(value):
                return True
        return False

    rec(tree)
    return found[0]


def plan_mutants(files: list[FileChange], root: str | Path = ".", test_dirs: list[str] | None = None,
                 max_mutants: int = 40) -> list[tuple[Mutant, str]]:
    """Return [(Mutant, mutated_module_source)] for lines the diff added, in file/line order."""
    root = Path(root)
    test_dirs = test_dirs or ["tests"]
    out: list[tuple[Mutant, str]] = []
    for f in files:
        if not f.path.endswith(".py") or f.status == "deleted" or f.binary:
            continue
        if any(f.path.startswith(d.rstrip("/") + "/") for d in test_dirs) or Path(f.path).name.startswith("test_"):
            continue
        p = root / f.path
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        changed = set(f.added_line_numbers)
        sites = list(_candidate_sites(tree, changed))
        sites.sort(key=lambda s: (s[0].lineno, getattr(s[0], "col_offset", 0), s[1]))
        for node, op, fn in sites:
            fresh = ast.parse(text)
            idx = _walk_index(tree, node)
            tr = _Replace(idx, fn)
            new_tree = ast.fix_missing_locations(tr.visit(fresh))
            if tr.before == tr.after:
                continue
            try:
                mutated = ast.unparse(new_tree)
                compile(mutated, f.path, "exec")
            except Exception:
                continue
            m = Mutant(id=f"M{len(out) + 1}", path=f.path, line=node.lineno, operator=op,
                       original=tr.before[:120], mutated=tr.after[:120])
            out.append((m, mutated))
            if len(out) >= max_mutants:
                return out
    return out


def _copy_tree(root: Path, dest: Path) -> None:
    def ignore(_d, names):
        return [n for n in names if n in _SKIP_DIRS or n.endswith(".pyc")]
    shutil.copytree(root, dest, ignore=ignore, dirs_exist_ok=True)


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, float]:
    t0 = time.monotonic()
    env = dict(os.environ, PYTHONPATH=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    try:
        rc = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        rc = -999
    return rc, time.monotonic() - t0


def run_mutation(files: list[FileChange], root: str | Path = ".", test_cmd: list[str] | None = None,
                 test_dirs: list[str] | None = None, max_mutants: int = 40, timeout_s: int = 60,
                 min_kill_ratio: float = 0.8) -> MutationReport:
    root = Path(root).resolve()
    test_cmd = test_cmd or [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    t_start = time.monotonic()
    planned = plan_mutants(files, root, test_dirs, max_mutants)
    report = MutationReport(verdict="NO_MUTANTS", min_kill_ratio=min_kill_ratio, test_command=" ".join(test_cmd))
    if not planned:
        report.seconds = round(time.monotonic() - t_start, 2)
        return report
    with tempfile.TemporaryDirectory(prefix="riskgate-mut-") as tmp:
        work = Path(tmp) / "repo"
        _copy_tree(root, work)
        rc, _ = _run(test_cmd, work, timeout_s)
        if rc != 0:
            report.verdict = "BASELINE_FAILED"
            report.baseline_ok = False
            report.mutants = [m for m, _ in planned]
            report.total = len(planned)
            report.seconds = round(time.monotonic() - t_start, 2)
            return report
        for m, mutated in planned:
            target = work / m.path
            original = target.read_text(encoding="utf-8")
            target.write_text(mutated, encoding="utf-8")
            try:
                rc, secs = _run(test_cmd, work, timeout_s)
            finally:
                target.write_text(original, encoding="utf-8")
            m.seconds = round(secs, 2)
            m.status = "timeout" if rc == -999 else ("killed" if rc != 0 else "survived")
            report.mutants.append(m)
    report.total = len(report.mutants)
    # A timeout means the mutant changed behaviour enough to hang the tests: count it as caught.
    report.killed = sum(1 for m in report.mutants if m.status in ("killed", "timeout"))
    report.survived = sum(1 for m in report.mutants if m.status == "survived")
    report.kill_ratio = round(report.killed / report.total, 3) if report.total else None
    report.verdict = "PROVEN" if report.kill_ratio is not None and report.kill_ratio >= min_kill_ratio else "WEAK"
    report.seconds = round(time.monotonic() - t_start, 2)
    return report


def render_markdown(r: MutationReport) -> str:
    icon = {"PROVEN": "✅", "WEAK": "⚠️", "NO_MUTANTS": "ℹ️", "BASELINE_FAILED": "❌"}[r.verdict]
    lines = [f"### {icon} Test proof: **{r.verdict}**"]
    if r.verdict == "NO_MUTANTS":
        lines.append("No mutable logic on the changed lines (docs, config or constants only).")
        return "\n".join(lines) + "\n"
    if r.verdict == "BASELINE_FAILED":
        lines.append("The test suite fails before any mutation, so test strength cannot be measured. Fix the tests first.")
        return "\n".join(lines) + "\n"
    pct = f"{r.kill_ratio * 100:.0f}%" if r.kill_ratio is not None else "n/a"
    lines.append(f"Planted **{r.total}** bugs on the lines this MR changed; the tests caught **{r.killed}** ({pct}). "
                 f"Policy requires ≥ {r.min_kill_ratio * 100:.0f}%.")
    lines += ["", "| # | Where | Bug planted | Result |", "|---|---|---|---|"]
    for m in r.mutants:
        res = {"killed": "caught", "timeout": "caught (timeout)", "survived": "**SURVIVED**"}.get(m.status, m.status)
        lines.append(f"| {m.id} | `{m.path}:{m.line}` | `{m.original}` → `{m.mutated}` | {res} |")
    survivors = [m for m in r.mutants if m.status == "survived"]
    if survivors:
        lines += ["", "**What the tests would not notice:** " + "; ".join(
            f"`{m.original}` becoming `{m.mutated}` (line {m.line})" for m in survivors[:5])]
    lines.append(f"\n_{r.seconds}s · `{r.test_command}` · generated by `riskgate mutate`_")
    return "\n".join(lines) + "\n"
