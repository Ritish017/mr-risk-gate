from riskgate.diffparse import FileChange
from riskgate.policy import DEFAULT_POLICY, load_policy
from riskgate.score import render_markdown, score_changes

P = DEFAULT_POLICY
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"  # built at runtime so scanners don't flag the test file


def fc(path, added=(), removed=(), status="modified"):
    return FileChange(path=path, status=status, added=list(added), removed=list(removed),
                      added_line_numbers=list(range(1, len(added) + 1)))


def test_docs_only_change_is_low():
    r = score_changes([fc("README.md", ["more docs"])], P)
    assert r.level == "LOW" and r.score == 0 and r.findings == []


def test_billing_change_without_tests_is_medium():
    r = score_changes([fc("tinyledger/billing.py", ["    return amount * 2"])], P)
    rules = {f.rule for f in r.findings}
    assert rules == {"sensitive-path", "no-test-change"}
    assert r.score == 45 and r.level == "MEDIUM"
    assert r.untested_sources == ["tinyledger/billing.py"]


def test_billing_change_with_tests_drops_untested_finding():
    r = score_changes([fc("tinyledger/billing.py", ["x"]), fc("tests/test_billing.py", ["assert 1"])], P)
    assert "no-test-change" not in {f.rule for f in r.findings}
    assert r.level == "LOW"


def test_secret_forces_high_even_if_score_low():
    r = score_changes([fc("notes.txt", [f"key = {FAKE_AWS}"])], P)
    assert r.level == "HIGH"
    assert r.findings[0].rule == "secret-aws-key" and r.findings[0].severity == "critical"


def test_weakened_tests_detected():
    r = score_changes([fc("tests/test_billing.py", removed=["    assert total == 1"], added=["    pass"])], P)
    assert "weakened-tests" in {f.rule for f in r.findings}


def test_ci_and_policy_changes_stack_to_high():
    files = [fc(".gitlab-ci.yml", ["x"]), fc("riskgate.json", ["y"]), fc(".gitlab/duo/flows/a.yaml", ["z"]),
             fc("tinyledger/billing.py", ["w"])]
    r = score_changes(files, P)
    assert r.score >= P["thresholds"]["high"] and r.level == "HIGH"


def test_policy_file_patterns_do_not_self_flag():
    r = score_changes([fc("riskgate.json", ['"regex": "AKIA[0-9A-Z]{16}"'])], P)
    assert all(not f.rule.startswith("secret") for f in r.findings)


def test_size_points_capped():
    r = score_changes([fc("README.md", ["l"] * 5000)], P)
    size = [f for f in r.findings if f.rule == "size"][0]
    assert size.points == P["size"]["max_points"]


def test_markdown_render_contains_level_and_reasons():
    r = score_changes([fc("tinyledger/billing.py", ["x"])], P)
    md = render_markdown(r)
    assert "MEDIUM" in md and "money calculation" in md and "| Points |" in md


def test_load_policy_overrides(tmp_path):
    p = tmp_path / "riskgate.json"
    p.write_text('{"thresholds": {"medium": 10, "high": 20}}')
    pol = load_policy(p)
    assert pol["thresholds"]["high"] == 20 and pol["smells"]  # untouched keys keep defaults
