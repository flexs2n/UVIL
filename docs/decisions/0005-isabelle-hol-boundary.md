# ADR 0005: Isabelle/HOL boundary — bundle pin, agreeing fragment, measured downgrades

- Status: accepted
- Date: 2026-09-09
- Deciders: UVIL maintainers
- Extends: 0002 (tool pinning), 0003 (Lean pinning — the twin policy)

## Context

M4 adds a second ITP. The pragmatic choice for this machine is
Isabelle/HOL: it ships a self-contained native Windows bundle (no opam).
The OpenTheory lesson governs the shape of the integration: cross-ITP
artifact exchange must stay within the fragment where the systems PROVABLY
agree, and disagreements must be measured, not hidden.

## Decision

1. **Isabelle is pinned to the current stable bundle**,
   `PINNED_ISABELLE = "Isabelle2025"` (`ISABELLE_VERSION_ID` records the
   version id inside kernel hashes). The adapter probes `UVIL_ISABELLE`,
   then PATH:
   - a present-but-different bundle is a **hard error**
     (`IsabelleVersionMismatch`);
   - a fully absent bundle raises `IsabelleNotInstalled`: CLI paths skip
     cleanly (exit 0), tests self-skip.
2. **The HOL-facing boundary is the provably-agreeing fragment** — the same
   policy as the Lean encoder (ADR 0003), mirrored structurally in
   `adapters/isabelle/encode.py`: linear Int arithmetic via `by arith`;
   `ite` on Int via HOL conditionals; Bool atoms as `p::bool` propositions
   via `by auto`; div/mod only with positive constant divisors (shared
   constant-pin propagation with the Lean encoder — Isabelle's `int`
   `div`/`mod` are floored and agree with SMT-LIB Euclidean div/mod exactly
   there). The tactic set is provisional until the live discovery tests run
   against the pinned bundle (they self-skip here — the bundle was not
   installed at M4 time).
3. **Non-portable fragments downgrade, measurably**: terms outside the
   boundary (nonlinear `*`, quantifier spines, Real, arrays/seq, opaque
   terms) emit I9 `lossy` + I7 `semantic-mismatch` — never a fabricated
   twin. The **downgrade rate is measured on the same whitelist corpus
   families as the Lean slice** (`corpora/isabelle/expected.json`: 188
   entries, `downgrade_rate = 0.5794`, IDENTICAL to the Lean slice — the
   boundary policies provably agree; the 5 mismatch entries are the same
   five).
4. **Attestation = `isabelle build` session exit-0** on a batched theory
   file (`theory ... imports Main begin <theorems> end`; batch size 20,
   startup amortization — discovery-timed when the bundle exists).
   `kernel_hash = sha256(theory-file bytes + Isabelle version id)`; a failed
   batch re-runs per theorem so failures attribute exactly. No code path
   upgrades a failed/timeout proof search to discharged — and nothing via
   Isabelle is ever `refuted` (a failed proof search produces no
   counterexample). The `nitpick`/`quickcheck` counterexample oracles remain
   CANDIDATES: counterexamples only become I6 when a live oracle yields a
   genuine model (not wired at M4 time — recorded, not faked).
5. **The M4 slice's committed status is honest pending**: the bundle was not
   installed at generation time, so `isabelle_status` is `pending` for the
   183 rendered twins and `attested`/`failed` never appears without the
   kernel having actually run. The offline replay (one batched build over
   all committed twins) is the exit criterion behind `pytest -m slow`.

## Consequences

- Installing the pinned bundle and running
  `tools/gen_isabelle_slice.py` + `pytest -m slow` converts pending →
  attested in one deliberate, reviewable step; the committed manifest never
  fabricates an attestation in between.
- The Isabelle adapter mirrors the Lean adapter's discipline (G1/G0, no
  cross-upgrade), so downstream consumers treat the two ITPs identically.
- `*.thy` files are byte-stable (`.gitattributes`), because kernel hashes
  commit to exact bytes.
