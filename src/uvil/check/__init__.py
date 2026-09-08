"""uvil-check: dispatch obligations to SMT backends, enforce discipline (M1).

`check` runs each obligation through the SMT adapter, updates I4 statuses,
emits I6 counterexamples (refuted) and I7 diagnostics (unknown/timeout/encode
failures), and returns everything plus an I8 Run with per-obligation verdicts.
`record` persists the artifacts into the CAS and appends a solver-verdict G1
ledger entry (no certificates yet - the Alethe/LFSC upgrade path is M4+).

Discipline defaults are deny-by-default: anything the adapter cannot prove
stays open with an I7; no code path maps unknown/timeout to discharged.
"""
