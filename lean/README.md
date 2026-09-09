# lean/ — Lean workspace (M3 + M4)

- `lean-toolchain` — the pinned toolchain (`leanprover/lean4:v4.33.1`, ADR 0002 /
  0003). The primary check path needs ONLY this file + elan: no Lake, no Mathlib.
- `UVIL/Core.lean` — the D1 verified-translator core (M4): the shared-theory Term
  AST as a deep embedding, the deep-embedded LIA target language
  (`mulLit`/`divConst`/`modConst` encode the subset restrictions in their
  syntax), the `encodeLia` translator, and the **preservation theorem**
  `Term.encodeLia_preserves` (`interp (encodeLia t) env = eval t env` — closed-term
  semantics preserved through the translator). Python mirror:
  `src/uvil/translate.py`; evidence recording: `uvil.check.translator`
  (kernel-checked I9 + G1); scope: LIA subset only (M5+ for anything else).
- `UVILTranslateProve.lean` — the `uvil-translate-prove` parity runner (consumes
  the s-expression fixture format on stdin; used by tests/test_translator.py).
- `lakefile.toml` — the root Lake project (no external dependencies):
  `cd lean && lake build UVIL uvil-translate-prove`.
- `pool/lakefile.toml` — OPTIONAL separate project for the Pantograph warm
  pool (`src/uvil/adapters/lean/pool.py`, enabled via `UVIL_PANTOGRAPH`).
  Kept separate in M4: a broken optional dependency must not block the D1
  targets. Re-pinned 2026-09-09 to the canonical mirror
  `leanprover/Pantograph` @ `dev` head `92d4818` (the old
  `streesha/pantograph` @ `master` pin was invalid - repo 404).

## Build the D1 targets

```
cd lean
lake build UVIL uvil-translate-prove
```

## Build the warm pool (optional)

```
cd lean/pool
lake update
lake build Pantograph repl
```

Build-probe status (2026-09-09): the pinned Pantograph dev head builds
cleanly on Windows under the shared `v4.33.1` toolchain, but the pool is
NOT yet wired end-to-end:

- the binary is `.lake/packages/Pantograph/.lake/build/bin/repl.exe`
  (named `repl`, not `pantograph-repl`); on Windows, put
  `~/.elan/toolchains/leanprover--lean4---v4.33.1/bin` on `PATH` first
  (the exe needs `libleanshared.dll`).
- wire-protocol drift: REPL 0.3.19 speaks `goal.start` / `goal.tactic` /
  `goal.print`; `pool.py` pins protocol v1 (`setup` / `proof_start` /
  `goals`), which matches no upstream release. Until `pool.py` adopts the
  current command names (M5 candidate), the live pool arm stays
  skip-if-absent: do not set `UVIL_PANTOGRAPH` to this binary and expect
  the live tests to pass.
