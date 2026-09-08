# UVIL

**Universal Verification Interchange Layer** — a neutral intermediate representation and
adapter architecture for the artifacts of software verification: specifications,
verification conditions / proof obligations, proof terms and certificates,
counterexamples, failure diagnostics, and verification runs.

UVIL is not a verifier. It is the *infrastructure layer below existing verifiers*, in
the role LLVM plays for compilers: not a better backend, but the substrate that makes
backend-pluralistic systems expressible at all.

Design spec: see `../draft.md` (§5 Design Specification, §6 Work Plan).

## Status

Early development. Milestones M0–M6 track the master implementation plan.

- **M0 (committed):** artifact models I1–I9, canonical JSON + content addressing,
  content-addressed store with Merkle tree, append-only guarantee ledger (G0–G4),
  theory and semantics-model registries, JSON Schema export, `uvil` CLI skeleton.
- **M1 (this snapshot):** minimal viable interchange — Boogie-subset import adapter
  (parser + pinned Dafny wrapper), SMT adapter (deterministic SMT-LIB2 encoding,
  pinned z3 backend + optional cvc5), I6 counterexamples, R2 spec-strength hook,
  `uvil check` with discipline enforcement and solver-verdict G1 ledger entries,
  and a 525-obligation corpus with expected verdicts (see `corpora/`).
  Exit criterion (draft P1): Boogie/Dafny program → UVIL obligations → solver
  verdict + counterexample → ledger G1, end to end — see
  `examples/dafny_to_cvc5/`.

## Install

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip ...
```

## Quick tour

```sh
uvil init                       # creates .uvil/ (object store + ledger)
uvil put examples/vec_push/obligation.json   # validate + store an artifact
uvil get uvil:obligation@1:<hash>            # fetch back, byte-identical
uvil schema obligation          # JSON Schema for an artifact type
uvil schema --all --out schemas/
uvil ledger append --ref uvil:... --guarantee G1 --tool z3 --version 4.13.0
uvil ledger verify
```

## Layout

```
src/uvil/
├── artifacts/   I1–I9 pydantic models, core assertion language, canonical hashing
├── adapters/    boogie (parser + dafny wrapper), smt (encode, z3/cvc5, cex, R2)
├── check/       uvil-check dispatch, discipline enforcement, ledger G1 recording
├── schemas/     generated JSON Schema (uvil.<type>.schema.json), versioned @1
├── store/       filesystem CAS + Merkle tree; obligation identity hash
├── ledger/      append-only guarantee ledger (G0–G4)
├── theories/    core theory registry (uvil.core.int, uvil.core.seq, …)
├── semmodels/   versioned semantics-model registry
└── cli/         `uvil` entrypoint (typer)
```

Tool versions are pinned (z3 5.1.0, Dafny 4.9.0, optional cvc5 via `UVIL_CVC5`) —
see `docs/decisions/0002-tool-pinning.md`.

## License

See `LICENSE`.
