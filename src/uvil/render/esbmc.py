"""Backend-native render: ESBMC trace (the M4 completion of the render pair).

The counterexample report travels verbatim from `backend_witness` (format
`esbmc-trace`, the M2 pre-registered format; payload = the raw report.json
text emitted by `--generate-json-report`) - it is never re-serialized, so
nothing the backend printed is lost. Scenario/TLC stays a loud
NotImplemented until a TLC backend exists.
"""

from __future__ import annotations

from ..artifacts import Counterexample

ESBMC_TRACE_FORMAT = "esbmc-trace"


def to_backend_render(cex: Counterexample) -> str:
    """Return the backend-native ESBMC report text, verbatim from the witness."""
    witness = cex.backend_witness
    if (
        cex.kind == "trace"
        and witness is not None
        and witness.format == ESBMC_TRACE_FORMAT
        and isinstance(witness.payload, str)
    ):
        return witness.payload
    fmt = witness.format if witness is not None else None
    raise NotImplementedError(
        f"no ESBMC backend render for counterexample kind={cex.kind!r} "
        f"(witness format={fmt!r}); only kind='trace' with an "
        f"{ESBMC_TRACE_FORMAT!r} witness is renderable"
    )
