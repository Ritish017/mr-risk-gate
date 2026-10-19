#!/usr/bin/env bash
# Reproduces the deterministic half of the demo locally (no GitLab, no LLM):
# a LOW-risk docs MR and a MEDIUM/HIGH-risk billing MR, scored exactly as the
# flow's triage stage and the mr_risk_score CI job score them.
set -euo pipefail
APP="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$APP/results}"
WORK="$(mktemp -d)"
mkdir -p "$OUT"
export PYTHONPATH="$APP" GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.com \
       GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.com
cp -r "$APP/tinyledger" "$APP/riskgate.json" "$WORK/"
mkdir -p "$WORK/tests" && cp "$APP/tests/conftest.py" "$APP/tests/test_tinyledger.py" "$WORK/tests/"
cd "$WORK"
git init -q -b main && git add -A && git commit -qm "chore: base"

echo "== MR A: docs only =="
git checkout -qb docs/readme
printf '# tinyledger\n\nInvoice totals API.\n' > README.md
git add -A && git commit -qm "docs: add readme"
python -m riskgate score --base main --head HEAD --json-out "$OUT/mr_a_risk.json" --md-out "$OUT/mr_a_risk.md"

echo "== MR B: loyalty discount touching money logic, no tests =="
git checkout -q main && git checkout -qb feat/loyalty-discount
cat >> tinyledger/billing.py <<'PY'


def loyalty_discount(amount, years):
    """1% off per loyalty year, capped at 15%."""
    pct = min(Decimal(years), Decimal("15"))
    return apply_discount(amount, pct)


def legacy_total(amount, tax):
    # TODO remove after migration
    return float(amount) * (1 + float(tax) / 100)
PY
git add -A && git commit -qm "feat(billing): loyalty discount"
set +e
python -m riskgate score --base main --head HEAD --json-out "$OUT/mr_b_risk.json" --md-out "$OUT/mr_b_risk.md" --fail-on HIGH
echo "exit code with --fail-on HIGH: $?"
set -e
python -m riskgate testgaps --base main --head HEAD --format json > "$OUT/mr_b_testgaps.json"
python -m riskgate testgaps --base main --head HEAD

echo "== Test proof: the test-author agent's first attempt (stand-in, see scripts/demo_tests/README.md) =="
cp "$APP/scripts/demo_tests/attempt1_weak.py" tests/test_billing_riskgate.py
git add -A && git commit -qm "test(riskgate): cover loyalty_discount, legacy_total"
python -m pytest -q -p no:cacheprovider tests | tail -1
python -m riskgate mutate --base main --head HEAD --json-out "$OUT/mr_b_mutation_attempt1.json" --md-out "$OUT/mr_b_mutation_attempt1.md" | sed -n 1,3p

echo "== Test proof: second attempt after the gate returned the surviving bugs =="
cp "$APP/scripts/demo_tests/attempt2_strong.py" tests/test_billing_riskgate.py
git add -A && git commit -qm "test(riskgate): pin loyalty cap and tax arithmetic"
python -m pytest -q -p no:cacheprovider tests | tail -1
python -m riskgate mutate --base main --head HEAD --json-out "$OUT/mr_b_mutation.json" --md-out "$OUT/mr_b_mutation.md" | sed -n 1,3p

echo "== Release notes + ledger + evidence =="
git log --format=%s main..HEAD | python -m riskgate notes --version "MR !2" --risk-level "$(python -c "import json;print(json.load(open('$OUT/mr_b_risk.json'))['level'])")" > "$OUT/mr_b_release_notes.md"
python -m riskgate ledger --report "docs/readme=$OUT/mr_a_risk.json" --report "feat/loyalty-discount=$OUT/mr_b_risk.json" \
  --mutation "feat/loyalty-discount=$OUT/mr_b_mutation.json" --out "$OUT/public"
NO_PROXY=127.0.0.1,localhost python -m pytest -q -p no:cacheprovider tests --junitxml="$OUT/junit.xml" > "$OUT/pytest_target_repo.txt" 2>&1 || true
python -m riskgate evidence --risk "$OUT/mr_b_risk.json" --junit "$OUT/junit.xml" --mutation "$OUT/mr_b_mutation.json" --out "$OUT/mr_b_evidence.md" > /dev/null
echo "Results written to $OUT"
rm -rf "$WORK"
