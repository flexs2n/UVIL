"""Lean 4 adapter: I4 sequents -> Lean theorems, pinned-kernel attestation.

Layout:
- `encode`  - obligation -> standalone Lean theorem (`by omega` scaffolding).
- `backend` - pinned `lean` compile backend + `LeanVerdict`.
- `beq`     - BEq statement-equivalence probe (R4 statement faithfulness).
- `pool`    - optional Pantograph warm-backend sessions (skip-if-absent).
"""
