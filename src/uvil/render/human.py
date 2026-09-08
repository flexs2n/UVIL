"""Human-readable render of I6/I7 artifacts.

Every render is permanently prefixed `[unverified human rendering]` (the M1
`UNVERIFIED_PREFIX` convention): a human rendering is an aid, never a guarantee.
Formats:
- Valuation  -> `name = value` lines (shared-theory scalar values)
- Trace      -> numbered steps with per-step vars + loc
- Scenario   -> TLC-style `State N: <vars>` behavior listing
- CounterSpec-> the strengthening formula via `to_smt`
- I7         -> `kind@file:line: native_message` (+ LLM slot when present)
"""

from __future__ import annotations

from ..adapters.smt.cex import UNVERIFIED_PREFIX, term_model_value
from ..artifacts import Counterexample, Diagnostic
from ..artifacts.counterexample import TraceState
from ..artifacts.terms import to_smt

_PREFIX = UNVERIFIED_PREFIX


def _vars_text(state: TraceState) -> str:
    return ", ".join(f"{name} = {value}" for name, value in state.vars.items())


def _loc_text(state: TraceState) -> str:
    return f" @ {state.loc}" if state.loc else ""


def _counterexample_human(cex: Counterexample) -> str:
    lines: list[str] = [_PREFIX]
    match cex.kind:
        case "valuation":
            lines.append("valuation:")
            for name, term in sorted((cex.valuation or {}).items()):
                lines.append(f"  {name} = {term_model_value(term)}")
        case "trace":
            lines.append("trace:")
            for i, state in enumerate(cex.trace or [], start=1):
                lines.append(f"  step {i}: {_vars_text(state)}{_loc_text(state)}")
        case "scenario":
            lines.append("scenario:")
            for i, state in enumerate(cex.scenario or [], start=1):
                lines.append(f"  State {i}: {_vars_text(state)}{_loc_text(state)}")
        case "counterspec":
            formula = to_smt(cex.counter_spec) if cex.counter_spec is not None else "<absent>"
            lines.append(f"counter_spec: {formula}")
    return "\n".join(lines)


def _diagnostic_human(diag: Diagnostic) -> str:
    loc = diag.loc
    head = f"{diag.kind}@{loc.file or '?'}:{loc.line if loc.line is not None else '?'}"
    lines = [_PREFIX, f"{head}: {diag.native_message}"]
    if diag.llm_explanation is not None:
        lines.append(f"  llm_explanation (unverified): {diag.llm_explanation.text}")
    return "\n".join(lines)


def to_human(artifact: Counterexample | Diagnostic) -> str:
    """Render an I6/I7 artifact as unverified human-readable text."""
    if isinstance(artifact, Counterexample):
        return _counterexample_human(artifact)
    if isinstance(artifact, Diagnostic):
        return _diagnostic_human(artifact)
    raise TypeError(f"to_human supports I6/I7 only, got: {type(artifact).__name__}")
