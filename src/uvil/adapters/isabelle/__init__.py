"""Isabelle/HOL adapter: the second ITP (M4).

Layout:
- `encode`  - the HOL-facing boundary: obligation -> HOL theorem line
  (`by arith`/`by auto`); out-of-boundary terms fail loud.
- `backend` - pinned Isabelle bundle (`isabelle build` session attestation,
  batched theory files, `kernel_hash = sha256(theory bytes + version id)`).

Mirrors the Lean adapter; the downgrade rate against the shared corpus
families is measured, never hidden (ADR 0005).
"""

from __future__ import annotations

from .backend import (
    ISABELLE_ENV_VAR,
    ISABELLE_VERSION_ID,
    PINNED_ISABELLE,
    IsabelleBackend,
    IsabelleNotInstalled,
    IsabelleVerdict,
    IsabelleVersionMismatch,
    isabelle_status,
    kernel_hash,
)
from .encode import (
    ISABELLE_BATCH_SIZE,
    TARGET_KIND,
    UnsupportedTermError,
    hol_statement,
    theorem_name,
    theory_file,
    to_hol_theorem,
)

__all__ = [
    "ISABELLE_BATCH_SIZE",
    "ISABELLE_ENV_VAR",
    "ISABELLE_VERSION_ID",
    "PINNED_ISABELLE",
    "TARGET_KIND",
    "IsabelleBackend",
    "IsabelleNotInstalled",
    "IsabelleVerdict",
    "IsabelleVersionMismatch",
    "UnsupportedTermError",
    "hol_statement",
    "isabelle_status",
    "kernel_hash",
    "theorem_name",
    "theory_file",
    "to_hol_theorem",
]
