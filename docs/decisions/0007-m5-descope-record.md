# ADR 0007: M5 scope record — descope, deferrals, and the open live-verification debts

- Status: accepted
- Date: 2026-09-09
- Deciders: UVIL maintainers
- Records: the master-plan M5 scope decisions (draft P4 protocol half + audit
  errata item 4); amends the M5 schedule, no prior ADR

## Context

The master-plan M5 milestone ("incremental protocol + adversarial benchmark")
carried several audit-added scope items whose size did not fit the milestone
once the four locked deliverables (the `protocol/` incremental check, the R2
LIA spec-strength checking, the churn benchmark + `uvil bench`, and the
Pantograph pool protocol v2) were sized against the M0–M4 baseline. Four
decision points were left open by the audit; this ADR records how they were
resolved on 2026-09-09.

## Decision

1. **R2 spec-strength translator: BUILT for the LIA shared-theory subset.**
   `adapters/smt/strength.py` executes the ADR 0006 descope decision: semantic
   clause-preservation probes (SMT implication checks over the pinned z3)
   replace the purely syntactic unmatched-clause verdict for the LIA subset.
   The arbitrary-spec (cross-theory) translator stays out of scope - the
   syntactic fast path and the conservative probe-outcome mapping
   (`unknown`/timeout ⇒ lossy + residual, never silently passed) are the
   enforcement contract.
2. **TLC/Scenario I6 producer: DESCOPED.** The `scenario` I6 shape stays
   fixture-rendered (the M2 renderers are unchanged); ESBMC's Trace producer
   (M4, ADR 0004) covers model-checking counterexamples, and no TLC/tla2tools
   integration is scheduled. No producer is planned for M6.
3. **VeriContest harvesting: DEFERRED to M6** (requires a Rust/Verus
   toolchain install; the corpus `Deferred` note is updated accordingly).
4. **Live-verification debts: only the Pantograph pool protocol update was
   closed in M5.** `pool.py` now speaks protocol v2 (REPL 0.3.x `goal.*`
   commands, discovery-pinned on the wire; the live arm passes against the
   built binary including the sorry gate - see `lean/README.md`). The
   **Isabelle bundle** live path and the **Strata-CLI** live path remain the
   two open live-verification debts (both skip-if-absent, recorded in
   `corpora/README.md`), to be closed in M6 or later.

   *Update 2026-09-11:* the **Isabelle live debt is CLOSED** — the pinned
   bundle attested the full slice (183/188; see ADR 0005 errata and
   `corpora/README.md`). The Strata-CLI live debt was exercised the same
   day: the pinned commit's CLI (`strata verify`, z3 5.1.0) ran on all 12
   committed artifacts with verdicts recorded verbatim as opaque I5
   payloads (`corpora/README.md` strata section).
5. **Aeneas semantics-model seed: registered.** `model:aeneas-functional.v1`
   joins the registry as a registry-only seed (no adapter consumes it yet) so
   the semantics-model slot is honest for future Rust/functional imports
   (the draft P1.3 deferred follow-up).

## Consequences

- The M5 exit criterion is the four locked deliverables; the descope items
  above do not count against it.
- draft.md is NOT amended for M5 (unlike ADR 0006's surgical edits): the
  descope record lives here and in `corpora/README.md`.
- The two open live-verification debts and the VeriContest deferral carry
  into the M6 hardening plan; closing them requires no schema changes.
- The churn benchmark's mutation families are documented as a degradation
  replay measuring PROTOCOL MECHANICS (cache-hit/survival), not
  toolchain-evolution fidelity; the headline metric is the downgrade rate
  (churned obligations that do not stay discharged - 0.000 on the committed
  corpus).
