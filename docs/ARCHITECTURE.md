# Architecture

```
 developer pushes / opens MR
            │
            ▼
 ┌──────────────────── GitLab CI/CD (.gitlab-ci.yml) ────────────────────┐
 │ lint → unit_tests(JUnit) → SAST + secret_detection → mr_risk_score    │
 │   → build_wheel → staging_smoke → [pages: manual production gate]     │
 │   → post_deploy_probe → (tags) release_notes → create_release         │
 │   → evidence_bundle (always)                                          │
 └───────────────────────────────────────────────────────────────────────┘
            │ MR created / reviewer assigned           │ pipeline failed
            ▼                                          ▼
 ┌──── Duo flow: mr-risk-gate ────┐        ┌── Duo flow: pipeline-medic ──┐
 │ risk_triage  (riskgate score)  │        │ diagnose (failing job logs)  │
 │   LOW ───────────────┐         │        │ remediate: fix on MR branch  │
 │   MEDIUM/HIGH        ▼         │        │   or MR note / new issue     │
 │ test_author (riskgate testgaps,│        └──────────────────────────────┘
 │   pytest, create_commit)       │
 │ release_scribe (riskgate notes,│        Release Captain (custom agent,
 │   label risk::*, summary note) │        read-only chat for the human)
 └────────────────────────────────┘
            │
            ▼
   human reviews summary → merges → runs manual `pages` job (production)
```

## Design choices
- **Deterministic gate before the LLM.** The scorer is pure Python with no network or model calls,
  so the same diff always gets the same verdict and the reasons are auditable. The LLM agents only
  run the expensive steps (writing tests) when the gate says it matters. LOW-risk MRs skip the
  test-author agent entirely, which also saves GitLab Credits.
- **Agents never merge or deploy.** No flow has merge/approve tools (`tests/test_flows.py` enforces
  this). Production is a manual CI job — this is what makes the project *Supervised*.
- **Loop safety.** GitLab triggers require a human actor, so pipelines started by the flows' own
  commits do not re-trigger Pipeline Medic.
- **Test gaps by AST, not text.** `testgaps` maps changed lines to functions with `ast` and counts a
  function as covered only if a test file uses its name in code (names, attributes, imports) —
  mentions in strings or comments don't count.
- **Evidence over claims.** `evidence` only reports values from CI variables and job artifacts and
  says "missing" otherwise.

## Fallbacks
- If built-in read tools fail inside a flow (reported by one participant as HTTP 404 in the
  hackathon group), the prompts tell agents to fall back to `git` + `riskgate` in the flow workspace.
- If hosted runners are unavailable in the hackathon group, register a project runner (see SETUP.md).

## Test proof (added 2026-10-15)
`riskgate mutate` closes the loop on agent-written tests. It maps the diff's added lines onto AST
nodes, generates one mutant per mutation site (stdlib `ast` + `ast.unparse`), copies the repo to a
temp dir once, swaps each mutated module in, runs the test command with a timeout, and restores the
file. Killed = test command non-zero (a timeout counts as killed); survived = tests still green.
The kill ratio is compared with `mutation.min_kill_ratio` in `riskgate.json`. The `test_author`
agent loops at most 2 extra rounds on survivors; CI's `mutation_proof` job re-runs it independently,
so the verdict in the evidence bundle doesn't depend on the agent's own report.
