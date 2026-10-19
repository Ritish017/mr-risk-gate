# Demo stand-ins for agent-written tests

These two files are **hand-written stand-ins** used only by `scripts/demo_local.sh`, so the
local demo is deterministic without an LLM. They imitate the two outcomes the `test_author`
agent can produce on GitLab:

- `attempt1_weak.py`: a test that passes but checks almost nothing (the failure mode we gate).
- `attempt2_strong.py`: tests that pin the behaviour of every changed line.

On GitLab, the real tests are written by the Duo `test_author` agent and judged by the same
`riskgate mutate` command.
