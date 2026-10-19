### 🟡 MR Risk Gate: **MEDIUM** (57/100)

1 files · +11 / -0 lines

| Points | Rule | Why | Where |
|---:|---|---|---|
| 25 | `sensitive-path` | touches money calculation (tinyledger/billing.py) | `tinyledger/billing.py` |
| 20 | `no-test-change` | source changed with no test changes: tinyledger/billing.py |  |
| 10 | `float-money` | float-money in added line | `tinyledger/billing.py`:56 |
| 2 | `todo` | todo in added line | `tinyledger/billing.py`:55 |

_Scored deterministically by `riskgate` against `riskgate.json`._