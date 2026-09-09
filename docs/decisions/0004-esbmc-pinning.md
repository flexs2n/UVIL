# ADR 0004: ESBMC pinning — release binary, verdict mapping, harness subset

- Status: accepted
- Date: 2026-09-09
- Deciders: UVIL maintainers
- Extends: 0002 (tool pinning)

## Context

M4 adds model checking (the Forge-pipeline third leg) via ESBMC, a bounded
model checker whose frontend is NOT Boogie: it compiles real C (its own
frontend + GOTO conversion). This makes it the cross-language case — a
backend that verifies artifacts no Boogie-only path could carry — but its
verdicts are model-checking run records, not deductive guarantees, and its
binary surface needed pinning.

## Decision

1. **ESBMC is pinned to the official release binary** `v8.5`
   (`PINNED_ESBMC = "8.5.0"`, release tag `v8.5`): the Windows asset
   `esbmc-windows.zip` carries sha256
   `626c91e587ec496d1e5fdc523cf8d557627af27087b4c13f0f3c241d286b3a55`.
   The adapter probes `UVIL_ESBMC`, then PATH, then the documented default
   install dir (`~/tools/esbmc-8.5/release/bin`):
   - a present-but-different ESBMC is a **hard error** (`EsbmcVersionMismatch`);
   - a fully absent binary raises `EsbmcNotInstalled`: CLI paths skip cleanly
     (exit 0), tests self-skip (the Dafny/Lean precedent).
2. **Verdict mapping is total and fail-loud** (`esbmc_status` is the single
   mapping point, unit-tested): `verified`/`violated`/`unknown` all leave the
   obligation `open`; `timeout` maps to `timeout`. **Model-checking results
   never discharge a deductive obligation and never refute one** — a violated
   harness is a bounded execution witness (I6 Trace + I7 `unproved` stating
   exactly that), not a deductive refutation; `record_esbmc` appends G1
   (model-checking run record with tool attestation, no kernel hash — no
   kernel participates) or G0, never G2+.
3. **Discovery-pinned CLI surface (v8.5, tests/test_esbmc_discovery.py):**
   verdict banners `VERIFICATION SUCCESSFUL`/`VERIFICATION FAILED` (exit 0/1)
   print on stderr; unparsable C exits nonzero with `PARSING ERROR` and maps
   to `unknown` (never upgraded); `--generate-json-report` emits `report.json`
   (process CWD) on a violation and nothing otherwise — the machine-readable
   surface `cex.py` parses into I6 Traces; **`--timeout` is unimplemented on
   Windows** so budgets are enforced by the subprocess layer; **`--bug-finding`
   does not exist in v8.5** (`unrecognised option`) — the plan's
   `[--bug-finding]` CLI option maps to the documented `--multi-property`
   mode instead.
4. **The C import subset is documented and small** (`import_c`): straight-line
   `int` code, `if`/`else` (path forking), bounded `for` (unrolled, budget 16),
   the three assertion call forms, and `__VERIFIER_nondet_int()` inputs.
   Sequent terms use the documented bounded-integer abstraction
   (`model:esbmc-goto.v1`: unbounded Int, Euclidean div/mod) — C 32-bit
   wraparound is intentionally NOT modeled in sequents, which is exactly why
   model-checking verdicts must never upgrade them. Anything else (arrays,
   pointers, `while`, function calls, bare-arithmetic conditions) surfaces as
   I7 `parse`/`semantic-mismatch` with the verbatim line; the parser is only
   for obligation extraction — ESBMC itself compiles the real source,
   untrusted.
5. **The corpus (`corpora/c`, 50 entries) is committed and live-verified**:
   every entry's expected verdict was reproduced by the pinned binary at
   generation time; the pointer/heap family demonstrates the cross-language
   capability (verified/violated purely through ESBMC's own pointer
   semantics).

## Consequences

- Upgrading ESBMC is a deliberate, reviewable change: bump the pin, re-run
  discovery, regenerate the corpus verdicts, re-verify the demo.
- CI may omit ESBMC: tool-dependent suites self-skip; the corpus and its
  manifest stay committed (never re-derived).
- The abstraction caveat (wraparound) is recorded on every imported artifact
  via the semantics-model reference — library mismatch stays a first-class,
  citable object.
