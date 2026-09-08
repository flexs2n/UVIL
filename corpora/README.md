# Corpora

Versioned corpora of obligations, failures, and expected verdicts.

## `boogie/` — M1 corpus (≥500 obligations)

- `*.bpl` — hand-curated Boogie programs (arithmetic identities, min/max/abs/clamp,
  loop-invariant sum/count, array bounds via `select`, map `store`/`select`,
  quantified ranges, mod/div reasoning, one intentional vacuity case, one timeout case).
- `generated/*.bpl` — deterministic parameterized instantiations of the same families
  (`tools/gen_corpus.py`, fixed seed). Regeneration is idempotent; generated files are
  committed.
- `expected.json` — `obligation_identity -> {file, family, expected, proc}` for every
  corpus obligation. Designed families match their by-construction verdicts; observed
  families (nonlinear unknowns, the timeout case) record exactly what the pinned z3
  (5.1.0) returned at generation time. Timeout-family entries never discharge.

Corpus discipline: one assert per procedure (the obligation-identity tuple is
per-procedure). Verdicts re-run with z3 under the corpus budgets (≤2s per obligation;
timeout cases isolated behind the pytest `slow` marker, run with `pytest -m slow`).

Verify without solving: `uvil corpus verify corpora/boogie`.

## Deferred

VeriContest artifact harvesting (Rust/Verus toolchain) is recorded as a corpus
follow-up for M4. See the master plan, M1 §4 and M2 §2.
