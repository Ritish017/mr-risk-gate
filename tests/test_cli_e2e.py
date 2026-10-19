"""End-to-end: real git repo, real commits, the CLI exactly as CI and the flow call it."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def run(cmd, cwd, **kw):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, **kw)


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(ROOT / "tinyledger", tmp_path / "tinyledger")
    (tmp_path / "tests").mkdir()
    shutil.copy(ROOT / "tests" / "test_tinyledger.py", tmp_path / "tests" / "test_tinyledger.py")
    shutil.copy(ROOT / "riskgate.json", tmp_path / "riskgate.json")
    run(["git", "init", "-q", "-b", "main"], tmp_path)
    run(["git", "add", "-A"], tmp_path)
    run(["git", "commit", "-qm", "chore: base"], tmp_path)
    return tmp_path


def rg(args, cwd):
    return run([sys.executable, "-m", "riskgate", *args], cwd)


def test_docs_change_scores_low(repo):
    (repo / "README.md").write_text("# hi\n")
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-qm", "docs: readme"], repo)
    r = rg(["score", "--base", "HEAD~1", "--format", "level"], repo)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "LOW"


def test_risky_billing_change_flags_and_finds_gap(repo):
    src = repo / "tinyledger" / "billing.py"
    src.write_text(src.read_text() + '''

def loyalty_discount(amount, years):
    """New: 1% per loyalty year, capped at 15%."""
    pct = min(Decimal(years), Decimal("15"))
    return apply_discount(amount, pct)
''')
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-qm", "feat(billing): loyalty discount"], repo)
    r = rg(["score", "--base", "HEAD~1", "--format", "json", "--dotenv-out", "risk.env", "--fail-on", "MEDIUM"], repo)
    rep = json.loads(r.stdout)
    assert r.returncode == 2  # --fail-on MEDIUM trips
    assert rep["level"] == "MEDIUM"
    assert {f["rule"] for f in rep["findings"]} >= {"sensitive-path", "no-test-change"}
    assert (repo / "risk.env").read_text().startswith("RISK_LEVEL=MEDIUM")
    g = rg(["testgaps", "--base", "HEAD~1", "--format", "json"], repo)
    data = json.loads(g.stdout)
    assert [u["function"] for u in data["untested"]] == ["loyalty_discount"]


def test_secret_in_commit_is_high(repo):
    (repo / "tinyledger" / "config.py").write_text('API_KEY = "' + "glpat-" + "a" * 24 + '"\n')
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-qm", "chore: config"], repo)
    r = rg(["score", "--base", "HEAD~1", "--format", "level"], repo)
    assert r.stdout.strip() == "HIGH"


def test_notes_and_ledger_commands(repo, tmp_path):
    commits = tmp_path / "c.txt"
    commits.write_text("feat: a\nfix: b\n")
    n = rg(["notes", "--version", "v0.1.0", "--commits", str(commits), "--risk-level", "LOW"], repo)
    assert "### Features" in n.stdout and "### Rollback plan" in n.stdout
    rj = tmp_path / "risk.json"
    rj.write_text(json.dumps({"level": "LOW", "score": 0, "files_changed": 1, "lines_added": 1,
                              "lines_removed": 0, "findings": []}))
    out = tmp_path / "public"
    l = rg(["ledger", "--report", f"abc={rj}", "--out", str(out)], repo)
    assert l.returncode == 0 and (out / "index.html").exists()
