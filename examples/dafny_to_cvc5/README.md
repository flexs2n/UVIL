# Demo: Boogie -> UVIL -> z3 (Dafny twin, skip-if-absent)

This demo walks the M1 exit criterion (draft P1): a third-party consumer checks
obligations *not authored in its home format* end-to-end:

    Boogie program -> UVIL I4 obligations -> z3 verdict + I6 counterexample
    -> ledger G1 entry

## The twin pair

- `vec_push.bpl` — the always-runnable path: a pure-Python Boogie-subset import,
  z3 (pinned 5.1.0) in-process. No external tools needed.
- `vec_push.dfy` — the same obligation authored in Dafny. When Dafny is installed
  at the pinned version (`PINNED_DAFNY` in `uvil/adapters/boogie/dafny.py`), it is
  translated to Boogie text (`dafny translate boogie --no-verify`) and fed through
  the *same* parser. Without Dafny, this path skips cleanly; with a wrong version
  it fails loudly (I7 `semantic-mismatch`, ADR 0002).

## Run the z3 path

```sh
uvil init
uvil check examples/dafny_to_cvc5/vec_push.bpl
```

Expected output: a verdict table (`discharged` for the in-bounds push) and
`run stored; ledger G1 appended (discharged=...)`. The I8 Run and all updated
artifacts live in `.uvil/`; the ledger entry attests tool/version
(solver-verdict G1 — no certificates; the Alethe/LFSC upgrade path is M4+).

Inspect the ledger:

```sh
uvil ledger verify
```

## Run the refutation path (counterexample back as an artifact)

```sh
uvil check corpora/boogie/refutable_linear.bpl
```

The refuted obligation produces an I6 `Valuation` counterexample with the raw
SMT-LIB model and an unverified human summary, stored in the CAS next to the run.

## Run the Dafny path (skip-if-absent)

```sh
dotnet tool install --global Dafny --version 4.9.0   # once; see ADR 0002
uvil translate examples/dafny_to_cvc5/vec_push.dfy --out examples/dafny_to_cvc5/out/
```

Real Dafny output frequently falls outside the documented M1 Boogie subset; when
it does, the CLI prints I7 `parse` diagnostics preserving the verbatim source
line — the fail-loud contract, never a silent skip.

## Corpus

`uvil corpus verify corpora/boogie` checks all 525 corpus identities against
`expected.json` (no solving); `pytest -m slow` re-runs the timeout family.
