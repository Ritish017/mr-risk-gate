from riskgate.notes import parse_commits, render_release_notes


def test_buckets_conventional_commits():
    b = parse_commits([
        "abc1234 feat(billing): add GST override",
        "fix: round half up",
        "feat!: drop float totals",
        "Merge branch 'x' into main",
        "random message",
    ])
    assert b["feat"] == ["**billing:** add GST override", "drop float totals"]
    assert b["fix"] == ["round half up"]
    assert b["breaking"] == ["drop float totals"]
    assert b["other"] == ["random message"]


def test_release_notes_include_risk_and_rollback():
    md = render_release_notes("v0.2.0", ["fix: x"], risk_level="HIGH")
    assert md.startswith("## v0.2.0")
    assert "**HIGH**" in md and "### Rollback plan" in md and "re-scores it below HIGH" in md


def test_low_risk_has_no_high_step():
    md = render_release_notes("v1", ["docs: y"], risk_level="LOW")
    assert "below HIGH" not in md and "### Documentation" in md
