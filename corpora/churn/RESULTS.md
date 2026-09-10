# Churn benchmark results

Deterministic metrics over the committed churn corpus (fixed seed;
regenerate with `python tools/gen_churn.py`, reproducible with `uvil bench`).

| metric | value | target |
|---|---|---|
| scenarios | 60 | - |
| obligations (churned runs) | 240 | - |
| cache-hit rate | 0.750 | >= 0.7 |
| no-op control hit rate | 1.000 | == 1.0 |
| churn survival | 0.500 | >= 0.3 |
| partition fidelity | 1.000 | == 1.0 |
| downgrade rate | 0.000 | == 0.0 |

Cache-hit rate = reused / obligations over the churned runs; churn
survival excludes the no-op-reorder control family. Downgrade rate
counts churned obligations that did not stay `discharged`.
