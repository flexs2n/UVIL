# Forge on UVIL — one artifact set, three backend families, zero bespoke glue

The M4 exit criterion (master plan P3): reproduce the Forge-style pipeline —
**deduction + model checking + theorem proving on ONE artifact set** — with
≤1 new adapter per backend, vs Forge's hand-built three-way glue.

## The artifact set

- `clamp.c` — a C harness for a clamp with a **real bug** (the upper clamp
  returns 9, so value preservation `c == x || c == 10` fails for inputs
  above 10).
- `clamp.bpl` — the distilled Boogie encoding of the same property, as an
  agent would first write it (faithfully mirroring the bug): z3 REFUTES it.
- `clamp_fixed.bpl` — the counterexample-driven REPAIR of the same encoding:
  z3 DISCHARGES it, and its Lean and Isabelle twins attest the same sequent.

All three describe the SAME verification subject; they interoperate only
through UVIL artifacts and the committed CLI.

## Walkthrough (every command verified against the pinned tools)

```bash
# 0. workspace
uvil init --state .uvil-forge

# 1. MODEL CHECKING: ESBMC compiles the real C and finds the bug, emitting
#    I6 Traces (backend_witness.format = "esbmc-trace")
uvil check-esbmc examples/forge_on_uvil/clamp.c --timeout-s 60 --state .uvil-forge
#    verdicts (esbmc 8.5.0; model-checking run record)
#    -> violated (bounded C semantics); ledger G1 = model-checking run
#       record - never a deductive refutation (the obligations stay open)

# 2. render a stored trace for repair agents (use the refs printed by step 1)
uvil get <cex-ref> --state .uvil-forge > clamp.cex.json
uvil render clamp.cex.json --form human
uvil render clamp.cex.json --form json    # common JSON (machine form)

# 3. DEDUCTION: the distilled encoding is checked by UVIL's OWN SMT backend
uvil check examples/forge_on_uvil/clamp.bpl --backend z3 --state .uvil-forge
#    -> refuted (z3 found x = 11 - the same bug family ESBMC's trace showed);
#       ledger G1 (solver verdict, I6 valuation witness)

# 4. the counterexample-driven repair (M2 harness consumes the SAME I6/I7
#    shapes) corrects the mirrored bug:
uvil check examples/forge_on_uvil/clamp_fixed.bpl --backend z3 --state .uvil-forge
#    -> discharged; ledger G1 (solver verdict)

# 5. THEOREM PROVING (twin 1): the discharged obligation's Lean twin,
#    attested by the pinned kernel (G1; G2 with the BEq faithfulness probe),
#    offline-replayable via `uvil attest <proof-ref>`
uvil check-lean examples/forge_on_uvil/clamp_fixed.bpl --state .uvil-forge
uvil attest <proof-ref> --state .uvil-forge

# 6. THEOREM PROVING (twin 2): the same sequent's Isabelle/HOL twin, attested
#    by the pinned bundle (G1); skips cleanly when the bundle is absent
uvil check-isabelle examples/forge_on_uvil/clamp_fixed.bpl --state .uvil-forge
#    skip: isabelle is not installed (pin: PINNED_ISABELLE)   <- honest skip
```

## Why this is the Forge pipeline without the glue

Forge's published pipeline ships **three hand-built, pipeline-specific
adapters** (model checking → deduction → proving), each re-implementing
artifact plumbing for its stage. Here:

- the C harness enters through ONE import (`uvil.adapters.esbmc.import_c`) —
  and the CHECK runs on the real C via ESBMC's own frontend (the
  cross-language case: the pointer/heap corpus families have NO Boogie
  lowering at all);
- the Boogie encodings enter through the SAME import interface used by every
  other Boogie/Dafny input (`uvil.adapters.boogie`) — the identical M1
  approximation documented there (assert-position obligations, no WP);
- the Lean and Isabelle twins are produced from the SAME I4 obligations by
  their single adapters — no per-pipeline statement translation;
- the ledger discipline keeps the evidence classes honest across the whole
  run: model-checking verdicts never discharge deductive obligations, SMT
  refutations are witnessed by I6s, and kernel attestations are
  offline-replayable.

The measured adapter metric (per-adapter LoC + capability notes) is
documented in `docs/adapter-metrics.md`.
