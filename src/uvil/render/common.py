"""Common-JSON render of I6 Counterexamples and I7 Diagnostics.

This is the machine form repair agents consume: one stable, sorted-key dict
shape per artifact type, independent of which backend produced the failure.
Terms are serialized as term JSON (`Term.model_dump(mode="json")`); the I7
`llm_explanation` slot always carries `unverified: true` (enforced upstream by
the frozen model). Renderers never invent data: absent shapes render as null.
"""

from __future__ import annotations

from typing import Any

from ..artifacts import Counterexample, Diagnostic
from ..artifacts.counterexample import TraceState
from ..artifacts.terms import Term

TraceJson = dict[str, Any]


def _term_json(term: Term) -> dict[str, Any]:
    return term.model_dump(mode="json")


def _state_json(state: TraceState) -> TraceJson:
    return state.model_dump(mode="json")


def _counterexample_json(cex: Counterexample) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "valuation": None,
        "trace": None,
        "scenario": None,
        "counter_spec": None,
    }
    match cex.kind:
        case "valuation":
            payload["valuation"] = {
                name: _term_json(term) for name, term in (cex.valuation or {}).items()
            }
        case "trace":
            payload["trace"] = [_state_json(s) for s in (cex.trace or [])]
        case "scenario":
            payload["scenario"] = [_state_json(s) for s in (cex.scenario or [])]
        case "counterspec":
            payload["counter_spec"] = (
                _term_json(cex.counter_spec) if cex.counter_spec is not None else None
            )
    witness = cex.backend_witness
    return {
        "uvil_type": cex.uvil_type,
        "kind": cex.kind,
        "obligation_ref": cex.obligation_ref,
        "backend_witness": {"format": witness.format} if witness is not None else None,
        **payload,
    }


def _diagnostic_json(diag: Diagnostic) -> dict[str, Any]:
    return {
        "uvil_type": diag.uvil_type,
        "kind": diag.kind,
        "obligation_ref": diag.obligation_ref,
        "loc": diag.loc.model_dump(mode="json"),
        "native_message": diag.native_message,
        "llm_explanation": (
            diag.llm_explanation.model_dump(mode="json")
            if diag.llm_explanation is not None
            else None
        ),
    }


def to_common_json(artifact: Counterexample | Diagnostic) -> dict[str, Any]:
    """Render an I6/I7 artifact to the common JSON form agents consume."""
    if isinstance(artifact, Counterexample):
        return _counterexample_json(artifact)
    if isinstance(artifact, Diagnostic):
        return _diagnostic_json(artifact)
    raise TypeError(f"to_common_json supports I6/I7 only, got: {type(artifact).__name__}")
