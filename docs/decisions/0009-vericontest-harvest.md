# ADR 0009: VeriContest harvest — ground truth + slice import (backend-invariance)

- Status: accepted
- Date: 2026-09-11
- Deciders: UVIL maintainers
- Closes: the ADR 0007 VeriContest deferral (M6 item, promoted)
- Extends: 0002 (tool pinning), 0003 (the twin/downgrade policy)

## Context

The VeriContest benchmark (arXiv:2605.08553; repo
`HIPREL-Group/VeriContest` — the planning-time `secure-foundations/VeriContest`
URL 404'd; the artifact repo was located via GitHub search and pinned)
provides 946+ LeetCode/Codeforces tasks with judge-accepted Rust,
expert-validated Verus specifications, Verus-checked proofs
(`verified.rs`), and positive/negative tests. Draft §6.1 claims
"end-to-end: conclusions are backend-invariant"; the harvest makes that
claim measurable: native Verus verdicts (ground truth) compared against
UVIL's own z3 re-dispatch on the shared fragment.

## Decision

1. **Tool pins (ADR 0002 discipline)**: `PINNED_VERUS_TAG =
   release/0.2026.09.06.8dea4a2`, commit `8dea4a2196ebf99449fe2f141a2fb30acae3f17c`,
   toolchain `1.98.0-x86_64-pc-windows-msvc` (rustup), Verus-side z3
   `4.16.0` (Verus hard-checks its z3 version; the UVIL-side solver stays
   the corpus pin `5.1.0` — the two coexist on PATH). A Windows release
   binary EXISTS (`verus-0.2026.09.06.8dea4a2-x86-win.zip`) — the
   build-from-source fallback was not needed (recorded per the ADR 0007
   risk note).
2. **Fetch**: `tools/fetch_vericontest.py` copies the first 100 task dirs
   of `benchmark/leetcode` (sorted stable-id order, no randomness) VERBATIM
   into `corpora/vericontest/upstream/` with `PROVENANCE.json` (repo,
   commit, license, selection rule; the WI-2 precedent).
3. **Ground-truth arm**: the pinned Verus runs on every committed
   `verified.rs`; the per-task native verdict (exit code + verbatim
   `verification results::` line) is a RUN RECORD in
   `corpora/vericontest/expected.json` — never an I5 proof and never an
   upgrade of anything.
4. **Import arm**: `adapters/verus/importer.py` documents the
   scalar-contract subset (`verus!{}` blocks; `fn` with scalar
   `i*`/`u*`/`bool` params; `requires`/`ensures`; straight-line
   `let`/assignment/`assert` bodies) and lowers it to the common-core I2/I3/I4
   shapes (`model:verus-subset.v1`, unbounded-Int sequents — the ESBMC
   harness-abstraction precedent; Verus's bounded machine semantics are
   intentionally not modeled). Everything else fails loud as I7
   `parse`/`semantic-mismatch` with the verbatim fragment — measured, never
   hidden.
5. **Comparison protocol**: per in-subset file, the UVIL z3 verdict per
   obligation vs the native Verus verdict — agreement recorded per entry in
   `expected.json` (`agree`/`disagree`); every disagreement would be a
   finding, never papered over. Slice generator
   `tools/gen_vericontest_slice.py` (deterministic, idempotent, committed
   output) + `tests/test_vericontest.py`.

## The measured outcome (2026-09-11)

- **All 1007 upstream `verified.rs` files are out of the scalar-contract
  subset** (scanned at fetch time: Seq/quantifier/loop/struct fragments in
  every task) — the upstream downgrade rate is **1.000** on the 100-task
  sample. This IS the honest headline (the ADR 0007 risk table anticipated
  it): competitive-programming proofs ARE loop/sequence-shaped, and the
  slice boundary reflects the fragment where the two systems provably
  agree.
- Consequently the upstream in-subset set is EMPTY; the agreement metric is
  carried by the `generated/` harnesses (the strata-corpus precedent):
  6 UVIL-authored in-subset procedures (4 safe + 2 refutable), one fn per
  file. **Native Verus vs UVIL-z3: 6/6 agreement** (4× verified/discharged,
  2× failed/refuted) at generation time.
- Native ground truth on the sample: 98 verified, 7 failed,
  1 unsupported-locally (a Verus language pre-check error).

## Consequences

- Draft §6.1's backend-invariance claim is backed by a real (small,
  in-subset) agreement number and an honest measured downgrade rate; the
  claim is a SLICE claim, not a all-946-tasks claim.
- `adapters/verus/` joins `docs/adapter-metrics.md` (LoC recount in the
  experiment pass).
- The Aeneas `model:aeneas-functional.v1` seed stays registry-only (this
  adapter registers `model:verus-subset.v1` instead — the harvest imports
  procedure CONTRACTS, not a functional translation).
- Schema byte-identity: the harvest adds corpora + a new adapter; no
  `artifacts/*.py` change.
