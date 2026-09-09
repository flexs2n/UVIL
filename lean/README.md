# lean/ — Lean workspace (M3)

- `lean-toolchain` — the pinned toolchain (`leanprover/lean4:v4.33.1`, ADR 0002 /
  0003). The primary check path needs ONLY this file + elan: no Lake, no Mathlib.
- `lakefile.toml` — OPTIONAL Pantograph Lake project for the warm-backend pool
  (`src/uvil/adapters/lean/pool.py`, enabled via `UVIL_PANTOGRAPH`). Pantograph
  does not currently build on Windows; the pool is skip-if-absent and the
  plain-lean attestation path is unaffected.

## Build the warm pool (optional)

```
cd lean
lake update
lake build
# the REPL binary lands under .lake/.../bin/pantograph-repl
# point UVIL_PANTOGRAPH at it, or wrap it in a script
```
