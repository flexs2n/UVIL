"""Strata import adapter: dialect artifacts -> I2/I3/I4 (M4, import only).

Layout:
- `import` - the documented `program Core` subset parser -> the common-core
  import shapes (reusing adapters.boogie.lower.ImportResult), with I7
  parse/semantic-mismatch diagnostics; plus the optional vendor verify probe
  (`UVIL_STRATA`, skip-if-absent) recording vendor verdicts as opaque I5
  payloads.

Strata is NOT a backend here (its Lean core overlaps M3's Lean path): import
only. See the module docstring of `importer.py` (named so because `import` is
a keyword) for the vendor-TCB caveat.
"""

from __future__ import annotations

from .importer import (
    PINNED_STRATA_COMMIT,
    PINNED_STRATA_TOOLCHAIN,
    STRATA_ENV_VAR,
    STRATA_REPO,
    STRATA_TARGET_PROFILE,
    VENDOR_PAYLOAD_FORMAT,
    StrataVerifyResult,
    find_strata,
    import_strata,
    strata_verify,
    vendor_result_proof,
)

__all__ = [
    "PINNED_STRATA_COMMIT",
    "PINNED_STRATA_TOOLCHAIN",
    "STRATA_ENV_VAR",
    "STRATA_REPO",
    "STRATA_TARGET_PROFILE",
    "VENDOR_PAYLOAD_FORMAT",
    "StrataVerifyResult",
    "find_strata",
    "import_strata",
    "strata_verify",
    "vendor_result_proof",
]
