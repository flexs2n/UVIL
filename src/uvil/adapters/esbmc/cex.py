"""ESBMC JSON report -> I6 Counterexample (kind=trace).

The pinned v8.5 `--generate-json-report` surface (discovery-pinned in
tests/test_esbmc_discovery.py): on a violation ESBMC writes a `report.json`
array; each entry carries `status` ("violation"), `steps[]` of types
`assignment` (lhs/rhs), `violation` (assertion comment/guard/cwe + message),
`assert`, and `assume`, plus `initial_values` and `source_files`. Only the
machine-readable report is consumed - the textual state trace is never
screen-scraped.

The I6 Trace carries one TraceState per report step (assignment values are
the verbatim rhs strings; violation steps carry the violated property
message). The complete report text travels verbatim in `backend_witness`
(format `esbmc-trace`, the M2 pre-registered format) so nothing the backend
printed is lost; `render/esbmc.py` returns it verbatim.
"""

from __future__ import annotations

import json
from pathlib import PurePath

from ...adapters.smt.cex import UNVERIFIED_PREFIX
from ...artifacts import Counterexample, Obligation
from ...artifacts.base import artifact_id
from ...artifacts.counterexample import BackendWitness, SharedRender, TraceState

ESBMC_TRACE_FORMAT = "esbmc-trace"


def parse_report_steps(report_text: str) -> list[TraceState]:
    """Extract one TraceState per report step from a raw report.json text."""
    results = json.loads(report_text)
    if not isinstance(results, list):
        raise ValueError(f"unexpected esbmc report shape: {type(results).__name__}")
    states: list[TraceState] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        for step in result.get("steps", []):
            if not isinstance(step, dict):
                continue
            states.append(_state_of(step))
    return states


def _state_of(step: dict[str, object]) -> TraceState:
    step_type = step.get("type", "")
    loc = _loc_of(step)
    assignment = step.get("assignment")
    if step_type == "assignment" and isinstance(assignment, dict):
        lhs = assignment.get("lhs")
        rhs = assignment.get("rhs")
        if isinstance(lhs, str) and isinstance(rhs, str):
            return TraceState(vars={lhs: rhs}, loc=loc)
    if step_type == "violation" and isinstance(step.get("message"), str):
        return TraceState(vars={"property": str(step["message"])}, loc=loc)
    return TraceState(vars={}, loc=loc)


def _loc_of(step: dict[str, object]) -> str | None:
    file = step.get("file")
    line = step.get("line")
    function = step.get("function")
    if not (isinstance(file, str) and isinstance(function, str)):
        return None
    name = PurePath(file).name
    return f"{name}:{line}:{function}" if isinstance(line, str) else f"{name}:{function}"


def build_trace(obl: Obligation, report_text: str) -> Counterexample:
    """Build the I6 Trace counterexample for a violated harness."""
    states = parse_report_steps(report_text)
    return Counterexample(
        obligation_ref=artifact_id(obl),
        kind="trace",
        trace=states,
        shared_render=SharedRender(
            human_summary=f"{UNVERIFIED_PREFIX}\ntrace with {len(states)} steps"
        ),
        backend_witness=BackendWitness(format=ESBMC_TRACE_FORMAT, payload=report_text),
    )
