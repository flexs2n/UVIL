# Repair-loop experiment results (deterministic stubs)

Interface demonstration, not repair power: both arms are deterministic
rule-based stubs scoped to the named corpus families. The measured claim
is interface uniformity - ONE standardized agent repairs z3 refutations
and Boogie-parser failures unchanged (the M2 exit criterion) - not that
de-scoping repairs are meaningful program fixes.

| arm | entries | successes | backend-specific agent LOC |
|---|---|---|---|
| standardized (common JSON, one agent) | 105 | 105 | 13 |
| native (raw backend text, per-backend agents) | 105 | 105 | 76 |

## Subsets

- refuted: 30 generated wrong-constant instances
- parse: 75 corpus entries from parse-if/parse-call/parse-uninterp/parse-type (parse-stray is outside the stubs' contract)

## Standardized-arm failures

- none

## Native-arm failures

- none
