"""Backend-native render: SMT-LIB model text (valuation witnesses).

The model text travels verbatim from `backend_witness` (format
`smt-lib2-model`) - it is never re-serialized, so nothing the backend printed
is lost. Dispatch lives in `render/__init__` (M4): Trace witnesses render via
`render/esbmc.py`; Scenario stays a loud NotImplemented until a TLC backend
exists.
"""

from __future__ import annotations

from ..artifacts import Counterexample

SMT_MODEL_FORMAT = "smt-lib2-model"


def to_backend_render(cex: Counterexample) -> str:
    """Return the backend-native SMT model text, verbatim from the witness."""
    witness = cex.backend_witness
    if (
        cex.kind == "valuation"
        and witness is not None
        and witness.format == SMT_MODEL_FORMAT
        and isinstance(witness.payload, str)
    ):
        return witness.payload
    fmt = witness.format if witness is not None else None
    raise NotImplementedError(
        f"no SMT backend render for counterexample kind={cex.kind!r} "
        f"(witness format={fmt!r}); Trace/Scenario backend renders arrive with "
        "ESBMC/TLC in M4"
    )
