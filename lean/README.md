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
  Kept separate in M4: Pantograph does not currently build on Windows and its
  upstream moved; a broken optional dependency must not block the D1 targets.

## Build the D1 targets

```
cd lean
lake build UVIL uvil-translate-prove
```

## Build the warm pool (optional)

```
cd lean/pool
lake update
lake build
# the REPL binary lands under .lake/.../bin/pantograph-repl
# point UVIL_PANTOGRAPH at it, or wrap it in a script
```
