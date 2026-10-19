"""riskgate mutate: diff-scoped mutation testing."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from riskgate.diffparse import FileChange, parse_unified_diff
from riskgate.mutate import plan_mutants, render_markdown, run_mutation

SRC = textwrap.dedent('''\
    from decimal import Decimal


    def untouched(a, b):
        return a + b


    def loyalty_discount(amount, years):
        pct = min(Decimal(years), Decimal("15"))
        return amount * (Decimal("100") - pct) / Decimal("100")


    def is_vip(years, spend):
        return years >= 5 and spend > 1000
    ''')

WEAK = textwrap.dedent('''\
    from decimal import Decimal
    from pkg.calc import loyalty_discount, is_vip


    def test_returns_something():
        assert loyalty_discount(Decimal("100"), 3) is not None
    ''')

STRONG = textwrap.dedent('''\
    from decimal import Decimal
    from pkg.calc import loyalty_discount, is_vip


    def test_discount_normal():
        assert loyalty_discount(Decimal("100"), 3) == Decimal("97")


    def test_discount_capped_at_15():
        assert loyalty_discount(Decimal("100"), 20) == Decimal("85")


    def test_discount_zero_years():
        assert loyalty_discount(Decimal("200"), 0) == Decimal("200")


    def test_vip_boundaries():
        assert is_vip(5, 1001)
        assert not is_vip(4, 5000)
        assert not is_vip(5, 1000)
        assert not is_vip(10, 10)
    ''')

CHANGED = list(range(8, 15))  # loyalty_discount + is_vip, not `untouched`


def make_repo(tmp_path: Path, test_src: str) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "calc.py").write_text(SRC)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(test_src)
    return tmp_path


def change():
    return [FileChange(path="pkg/calc.py", added=["x"] * len(CHANGED), added_line_numbers=CHANGED)]


def test_plan_only_touches_changed_lines(tmp_path):
    root = make_repo(tmp_path, WEAK)
    planned = plan_mutants(change(), root)
    assert planned, "expected mutants on the changed lines"
    lines = {m.line for m, _ in planned}
    assert lines <= set(CHANGED)
    assert 5 not in lines  # `untouched` body is never mutated
    ops = {m.operator for m, _ in planned}
    assert "call min->max" in ops
    assert any(o.startswith("compare") for o in ops)
    assert "boolop And->Or" in ops
    assert "numeric string +1" in ops
    # every mutant is valid Python and differs from the original
    for m, src in planned:
        compile(src, m.path, "exec")
        assert m.original != m.mutated


def test_weak_tests_are_flagged_with_survivors(tmp_path):
    root = make_repo(tmp_path, WEAK)
    r = run_mutation(change(), root, timeout_s=60)
    assert r.baseline_ok
    assert r.verdict == "WEAK"
    assert r.survived > 0 and r.killed + r.survived == r.total
    md = render_markdown(r)
    assert "SURVIVED" in md and "would not notice" in md
    # the working tree is never modified
    assert (root / "pkg" / "calc.py").read_text() == SRC


def test_strong_tests_are_proven(tmp_path):
    root = make_repo(tmp_path, STRONG)
    r = run_mutation(change(), root, timeout_s=60)
    assert r.verdict == "PROVEN", render_markdown(r)
    assert r.kill_ratio >= 0.8


def test_no_logic_changes_means_no_mutants(tmp_path):
    root = make_repo(tmp_path, WEAK)
    files = [FileChange(path="README.md", added=["hi"], added_line_numbers=[1])]
    r = run_mutation(files, root)
    assert r.verdict == "NO_MUTANTS" and r.total == 0
    assert "No mutable logic" in render_markdown(r)


def test_failing_baseline_is_reported_not_scored(tmp_path):
    root = make_repo(tmp_path, "def test_broken():\n    assert False\n")
    r = run_mutation(change(), root)
    assert r.verdict == "BASELINE_FAILED" and not r.baseline_ok
    assert r.kill_ratio is None


def test_max_mutants_cap(tmp_path):
    root = make_repo(tmp_path, WEAK)
    assert len(plan_mutants(change(), root, max_mutants=3)) == 3


def test_cli_mutate_from_diff(tmp_path):
    root = make_repo(tmp_path, STRONG)
    diff = "diff --git a/pkg/calc.py b/pkg/calc.py\n--- a/pkg/calc.py\n+++ b/pkg/calc.py\n@@ -7,0 +8,7 @@\n" + \
        "".join("+" + l + "\n" for l in SRC.splitlines()[7:14])
    assert parse_unified_diff(diff)[0].added_line_numbers == CHANGED
    (root / "mr.diff").write_text(diff)
    app = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-m", "riskgate", "mutate", "--diff", "mr.diff", "--format", "json",
                          "--json-out", "mut.json", "--fail-on-weak"],
                         cwd=root, capture_output=True, text=True, env={"PYTHONPATH": str(app), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    assert out.returncode == 0, out.stderr
    data = json.loads((root / "mut.json").read_text())
    assert data["verdict"] == "PROVEN" and data["total"] >= 6
