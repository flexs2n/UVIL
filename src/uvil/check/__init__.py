"""uvil-check: dispatch obligations to SMT backends, enforce discipline (M1).

`check` runs each obligation through the SMT adapter, updates I4 statuses,
emits I6 counterexamples (refuted) + I7 diagnostics (refuted/unknown/timeout/
encode failures), and returns everything plus an I8 Run with per-obligation
verdicts. `record` persists the artifacts into the CAS and appends a
solver-verdict G1 ledger entry (no certificates yet - the Alethe/LFSC upgrade
path is M4+).

Discipline defaults are deny-by-default: anything the adapter cannot prove
stays open with an I7; no code path maps unknown/timeout to discharged.

M2 additions: refuted obligations now also carry an I7 `unproved` diagnostic
referencing their I6 witness, and `shadows.evaluate_shadows` evaluates a spec's
shadow set (R4) - vacuity probes that only downgrade (emit `vacuous` I7 +
CounterSpec I6), never upgrade.
"""
