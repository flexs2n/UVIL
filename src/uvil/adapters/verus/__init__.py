"""Verus import adapter: Verus/Rust artifacts -> I2/I3/I4 (M6, import only).

Layout:
- `import` - the documented Verus scalar-contract subset parser -> the
  common-core import shapes (reusing adapters.boogie.lower.ImportResult),
  with I7 parse/semantic-mismatch diagnostics (fail loud).

Verus is NOT a backend here (its own VC pipeline over its own z3 is the
COMPARISON arm of the VeriContest harvest, never a guarantee): import only.
See the module docstring of `importer.py` for the vendor-TCB caveat and the
pins.
"""

from __future__ import annotations

from .importer import (
    PINNED_VERUS_COMMIT,
    PINNED_VERUS_TAG,
    PINNED_VERUS_TOOLCHAIN,
    PINNED_VERUS_Z3,
    VERUS_ENV_VAR,
    VERUS_REPO,
    VERUS_TARGET_PROFILE,
    VerusImportError,
    VerusRunResult,
    find_verus,
    import_verus,
    verus_verify,
)

__all__ = [
    "PINNED_VERUS_COMMIT",
    "PINNED_VERUS_TAG",
    "PINNED_VERUS_TOOLCHAIN",
    "PINNED_VERUS_Z3",
    "VERUS_ENV_VAR",
    "VERUS_REPO",
    "VERUS_TARGET_PROFILE",
    "VerusImportError",
    "VerusRunResult",
    "find_verus",
    "import_verus",
    "verus_verify",
]
