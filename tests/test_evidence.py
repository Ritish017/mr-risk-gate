import json

from riskgate.evidence import build_evidence, junit_summary

JUNIT = """<?xml version="1.0"?><testsuites><testsuite name="a" tests="5" failures="1" errors="0" skipped="1"/>
<testsuite name="b" tests="2" failures="0" errors="1" skipped="0"/></testsuites>"""


def test_junit_summary(tmp_path):
    p = tmp_path / "junit.xml"
    p.write_text(JUNIT)
    assert junit_summary(p) == {"tests": 7, "failures": 1, "errors": 1, "skipped": 1}
    assert junit_summary(tmp_path / "missing.xml") is None


def test_bundle_reports_real_values_and_missing_inputs(tmp_path):
    risk = tmp_path / "risk.json"
    risk.write_text(json.dumps({"level": "MEDIUM", "score": 45,
                                "findings": [{"points": 25, "rule": "sensitive-path", "reason": "touches money"}]}))
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    sec = tmp_path / "gl-secret-detection-report.json"
    sec.write_text(json.dumps({"vulnerabilities": [{"severity": "High"}, {"severity": "High"}]}))
    md = build_evidence(risk, junit, [sec, tmp_path / "gl-sast-report.json"],
                        env={"CI_PROJECT_PATH": "g/p", "CI_COMMIT_SHA": "deadbeef"})
    assert "| Project | g/p |" in md and "deadbeef" in md
    assert "**MEDIUM** (45/100)" in md and "touches money" in md
    assert "7 tests, 1 failures, 1 errors, 1 skipped" in md
    assert "High: 2" in md and "`gl-sast-report.json`: _report missing_" in md
    assert "| Pipeline | _not available_ |" in md


def test_bundle_without_risk_report(tmp_path):
    md = build_evidence(tmp_path / "risk.json", tmp_path / "junit.xml", [], env={})
    assert "risk report missing" in md and "JUnit report missing" in md


def test_bundle_includes_mutation_proof(tmp_path):
    mut = tmp_path / "mutation.json"
    mut.write_text(json.dumps({"verdict": "WEAK", "killed": 3, "total": 5, "min_kill_ratio": 0.8, "mutants": [
        {"status": "survived", "path": "a.py", "line": 4, "original": "min(x, 15)", "mutated": "max(x, 15)"},
        {"status": "killed", "path": "a.py", "line": 5, "original": "a + b", "mutated": "a - b"}]}))
    md = build_evidence(tmp_path / "risk.json", tmp_path / "junit.xml", [], env={}, mutation_json=mut)
    assert "**WEAK**: 3/5 bugs planted" in md and "survived: `a.py:4` `min(x, 15)` → `max(x, 15)`" in md
    assert "a - b" not in md
    assert "_mutation report missing_" in build_evidence(tmp_path / "r", tmp_path / "j", [], env={},
                                                         mutation_json=tmp_path / "nope.json")
