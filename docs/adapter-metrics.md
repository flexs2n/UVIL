# Adapter metrics — the Forge-pipeline exit criterion (M4)

The master plan's M4 exit criterion: reproduce the Forge-style pipeline
(deduction + model checking + theorem proving on ONE artifact set) with
**≤1 new adapter per backend**, vs Forge's hand-built three-way glue.
Live walkthrough: `examples/forge_on_uvil/`.

## The adapter-count metric

| Pipeline | Adapters | Nature |
|---|---|---|
| **Forge** | 3 (model checking / deduction / proving) | hand-built, pipeline-specific: each stage re-implements artifact plumbing + statement translation for its leg; none reusable outside the pipeline |
| **UVIL** | ≤1 per backend, to a common core | each adapter maps ONE external tool's surface onto the shared artifact models (I1–I9); any pipeline over the same backends reuses them |

UVIL backends and adapters (per-adapter Python LoC, `src/uvil/adapters/*`):

| Adapter | LoC | Role | Capability notes |
|---|---|---|---|
| `boogie/` | 1206 | import frontend | documented Boogie subset parser + pinned Dafny wrapper; M1 no-WP obligation discipline (assert-position obligations); common import shapes (`ImportResult`) REUSED by the Strata adapter |
| `smt/` | 543 | backend | in-process z3 (pinned) + optional cvc5; total verdict mapping (unknown/timeout never discharge); I6 valuation counterexamples; R2 hook + D2 round-trip |
| `lean/` | 787 | second backend (ITP) | omega-subset encoder, pinned-kernel attestation (offline replay), BEq statement-faithfulness probe (G2), optional Pantograph warm pool |
| `esbmc/` | 1233 | backend (model checking, cross-language) | pinned release binary; total `esbmc_status` mapping — model-checking verdicts NEVER discharge/refute deductive obligations; JSON-report → I6 Trace (M2 pre-registered `esbmc-trace` format); documented C harness subset (obligation extraction only — ESBMC compiles the real source, untrusted); pointer/heap corpus families verified via ESBMC's own semantics (no Boogie lowering exists) |
| `strata/` | 625 | import frontend (vendor-TCB caveat) | real pinned-checkout artifacts; reuses the boogie import shapes; vendor verdicts recorded verbatim as opaque I5 payloads (`independent=False`), never trusted for guarantees |
| `isabelle/` | 503 | backend (ITP) | HOL-facing boundary (the provably-agreeing fragment, structurally mirroring the Lean encoder); `isabelle build` session attestation; measured downgrade rate (lossy I9s), identical to the Lean slice |

Common core (shared by ALL adapters, written once): the I1–I9 artifact
models, the canonical hashing/CAS/Merkle store, the guarantee ledger
(G0–G4), the render layer (common JSON + human + backend-native), and the
frozen schemas.

## What the metric buys

- Adding a pipeline over existing backends costs ZERO new adapters (the
  Forge demo is a pure CLI composition over the same artifact set).
- Adding a backend costs exactly one adapter, whose failure modes are the
  fail-loud ones (out-of-subset → I7, downgrades → measured lossy I9s,
  verdicts → total mappings unit-tested for the no-upgrade invariant).
- Vendor trust is explicit per adapter: Strata is a frontend (vendor Lean
  core, `independent=False` payloads); ESBMC verdicts are run records; ITP
  proofs are kernel attestations; SMT verdicts are solver verdicts (G1 —
  the certificate-checking upgrade path is M5+).
