"""ESBMC adapter: bounded model checking of C harnesses (M4).

Layout:
- `backend`  - pinned ESBMC binary runner + `EsbmcVerdict` + the total
  `esbmc_status` mapping (model-checking verdicts never discharge/refute).
- `cex`      - the pinned `--generate-json-report` surface -> I6 `Trace`
  (`backend_witness.format="esbmc-trace"`, the M2 pre-registered format).
- `import_c` - a documented C assertion subset -> I2/I3/I4 (obligation
  extraction only; ESBMC compiles the real source, untrusted).

Vendor-TCB note: ESBMC is an independent checker (own frontend, no Boogie);
its verdicts are recorded as run records, never as deductive upgrades.
"""

from __future__ import annotations

from .backend import (
    ESBMC_ENV_VAR,
    ESBMC_RELEASE_TAG,
    PINNED_ESBMC,
    EsbmcBackend,
    EsbmcNotInstalled,
    EsbmcVerdict,
    EsbmcVersionMismatch,
    esbmc_status,
    find_esbmc,
)
from .cex import ESBMC_TRACE_FORMAT, build_trace, parse_report_steps
from .import_c import CImportResult, CParseError, import_c

__all__ = [
    "ESBMC_ENV_VAR",
    "ESBMC_RELEASE_TAG",
    "ESBMC_TRACE_FORMAT",
    "PINNED_ESBMC",
    "CImportResult",
    "CParseError",
    "EsbmcBackend",
    "EsbmcNotInstalled",
    "EsbmcVerdict",
    "EsbmcVersionMismatch",
    "build_trace",
    "esbmc_status",
    "find_esbmc",
    "import_c",
    "parse_report_steps",
]
