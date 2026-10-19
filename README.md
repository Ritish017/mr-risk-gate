# MR Risk Gate

> Working name — rename before submitting.

**Agents write the tests. Risk Gate proves they would catch a bug.**

Agent-written tests pass easily and can still assert almost nothing. MR Risk Gate scores every merge
request, sends the risky ones to a Duo test-author agent, and then **plants small bugs on exactly the
lines the MR changed** (`min`→`max`, `'15'`→`'16'`, `+`→`-`, `>=`→`>` …) to check the new tests catch
them. Tests that let bugs through go back to the agent with the list of what they missed.

In the local demo run, the stand-in for the agent's first tests passed but caught **2 of 9** planted
bugs (WEAK). After the gate returned the survivors, the second attempt caught **9 of 9** (PROVEN). See
`results/mr_b_mutation_attempt1.md` and `results/mr_b_mutation.md`.

**Spend agent and reviewer effort where the risk is.** A deterministic, explainable risk engine
(`riskgate`) scores every merge request from its real diff against a policy file the team owns;
GitLab Duo Agent Platform flows then decide what to do with that score — write the missing tests,
diagnose failed pipelines, draft release notes and a rollback plan — while a human approves the
outcome (merge + manual production job).

Built for the GitLab Transcend **Life After Code** hackathon · Path A (Start Fresh) · **Supervised** autonomy.

## What runs where

| Piece | Where | What it does |
|---|---|---|
| `riskgate` (Python, stdlib only) | CI jobs + inside Duo flows via `run_command` | `score`, `testgaps`, **`mutate`**, `notes`, `evidence`, `ledger`, `probe` |
| `.gitlab/duo/flows/mr-risk-gate.yaml` | Duo custom flow, triggers: MR created / reviewer assigned | triage → (LOW) release scribe, (MEDIUM/HIGH) test author ⟲ `riskgate mutate` until PROVEN (max 3 rounds) → release scribe |
| `.gitlab/duo/flows/pipeline-medic.yaml` | Duo custom flow, trigger: pipeline failed | diagnose job logs → minimal fix on MR branch, or MR note / issue |
| `.gitlab/duo/agents/release-captain.yaml` | Duo custom agent (Agentic Chat) | read-only "is this safe to ship?" answers from the evidence |
| `.gitlab-ci.yml` | GitLab CI/CD | lint · test · secure (SAST, Secret Detection) · risk · package · deploy · monitor · release · govern |
| `tinyledger/` | demo target service | small invoice API the demo MRs change |

## DevSecOps stages touched
plan (risk labels on MRs, issues from Pipeline Medic) · create (agent-authored tests) · verify (pytest + JUnit,
staging smoke) · package (wheel → project PyPI registry on tags) · secure (SAST, Secret Detection, riskgate
secret/smell rules) · release (GitLab Release with generated notes) · configure (policy-as-code
`riskgate.json`, `production` environment) · monitor (post-deploy probe of the Pages site) · govern
(evidence bundle artifact, risk ledger).

## Quick start (local)
```bash
python -m pip install pytest pyyaml        # test-only deps; riskgate itself has none
python -m pytest -q                         # 60 tests
bash scripts/demo_local.sh                  # scores a LOW and a MEDIUM demo MR into results/
python -m riskgate score --base main --head HEAD     # score your own branch
python -m riskgate testgaps --base main --head HEAD  # changed functions with no test references
python -m riskgate mutate --base main --head HEAD    # plant bugs on changed lines, check the tests catch them
```

## Risk policy
`riskgate.json` lists sensitive paths (money logic, CI config, flow config, dependencies, the policy
itself), smell/secret regexes, and thresholds (MEDIUM ≥ 35, HIGH ≥ 65; any critical secret ⇒ HIGH).
Every point in a score carries its reason, so the triage note explains itself.

## Test proof (`riskgate mutate`)
- Mutation sites only on lines the diff **added**: arithmetic, comparisons, `and`/`or`, `min`/`max`,
  `any`/`all`, `not`, numeric literals (including `Decimal("15")`-style strings) and `return` values.
- Each mutant runs the test command in a scratch copy of the repo. The working tree is never touched.
- Verdicts: `PROVEN` (kill ratio ≥ `mutation.min_kill_ratio`, default 0.8), `WEAK` (lists the surviving
  bugs), `NO_MUTANTS` (docs/config only), `BASELINE_FAILED` (tests already red).
- Used by the Duo `test_author` agent (retry loop), the `mutation_proof` CI job, the evidence bundle and
  the ledger's "Test proof" column.

## Setting it up on GitLab
See [docs/SETUP.md](docs/SETUP.md). Architecture and design choices: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status / honesty
- `riskgate`, the CI file and the tests are complete and pass locally: 60/60 (see `results/pytest_riskgate_repo.txt`).
- The weak/strong test files in `scripts/demo_tests/` are hand-written stand-ins so the local demo is
  deterministic. On GitLab the tests come from the Duo agent.
- The Duo flows are written to the documented flow-registry v1 schema and validated offline
  (`tests/test_flows.py`); they still need a run on GitLab.com to be demonstrated.

## License
MIT — see [LICENSE](LICENSE).
