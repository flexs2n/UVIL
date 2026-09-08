"""Repair-loop harness: one agent interface, any backend (M2 exit criterion).

Agent protocol (the single interface; no backend fields beyond what I6/I7
already carry):

    feedback = {
        "diagnostics":    [<I7 common-JSON>, ...],
        "counterexamples": [<I6 common-JSON>, ...],
    }
    RepairAgent.repair(source: str, feedback: dict) -> str | None

Loop semantics (deterministic):
    import -> parse diagnostics? feed back
            : no obligations left? success (claim de-scoped)
            : check -> all discharged? success
            : feed back (I7s + I6s via render.common) -> agent repairs -> repeat
    `None` from the agent, an unchanged source, or an exhausted iteration
    budget ends the loop as a give-up.

`feedback_form="native"` runs the *native arm* of the experiment: instead of
the standardized common JSON the agent receives raw backend text
(`z3_model`: verbatim SMT-LIB model; `boogie_errors`: raw parser error line +
message). That is the bespoke per-backend path the standardized interface
replaces. No LLM/network calls; a real agent plugs in behind the same
`RepairAgent` protocol without touching the harness.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import ImportResult, import_module  # noqa: E402
from uvil.check.core import CheckResult, check  # noqa: E402
from uvil.render import to_common_json  # noqa: E402

COMMON_FORM = "common"
NATIVE_FORM = "native"

FeedbackForm = str  # COMMON_FORM | NATIVE_FORM (validated at runtime)


class RepairAgent(Protocol):
    """The single interface every repair agent implements."""

    def repair(self, source: str, feedback: dict[str, Any]) -> str | None: ...


@dataclass
class LoopOutcome:
    success: bool
    iterations: int
    stop_reason: str
    final_source: str | None


def _common_feedback(imported: ImportResult, checked: CheckResult | None) -> dict[str, Any]:
    if not imported.ok:
        return {
            "diagnostics": [to_common_json(d) for d in imported.diagnostics],
            "counterexamples": [],
        }
    assert checked is not None
    return {
        "diagnostics": [to_common_json(d) for d in checked.diagnostics],
        "counterexamples": [to_common_json(c) for c in checked.counterexamples],
    }


def _native_feedback(imported: ImportResult, checked: CheckResult | None) -> dict[str, Any]:
    if not imported.ok:
        return {
            "boogie_errors": [
                {"line": d.loc.line, "message": d.native_message} for d in imported.diagnostics
            ],
            "z3_model": None,
        }
    assert checked is not None
    model = None
    for cex in checked.counterexamples:
        if cex.backend_witness is not None and isinstance(cex.backend_witness.payload, str):
            model = cex.backend_witness.payload
            break
    return {"boogie_errors": [], "z3_model": model}


def run_loop(
    source: str,
    agent: RepairAgent,
    max_iterations: int = 5,
    backend: str = "z3",
    feedback_form: FeedbackForm = COMMON_FORM,
) -> LoopOutcome:
    """Drive import -> check -> repair until discharged, de-scoped, or give-up."""
    if feedback_form not in (COMMON_FORM, NATIVE_FORM):
        raise ValueError(f"unknown feedback form: {feedback_form!r}")
    build = _common_feedback if feedback_form == COMMON_FORM else _native_feedback
    current = source
    for iteration in range(1, max_iterations + 1):
        imported = import_module(current, "repair_loop.bpl")
        checked: CheckResult | None = None
        if imported.ok:
            if not imported.obligations:
                return LoopOutcome(True, iteration, "de-scoped: no obligations remain", current)
            checked = check(imported.obligations, backend=backend)
            assert checked.run is not None
            if all(v.status == "discharged" for v in checked.run.verdicts):
                return LoopOutcome(True, iteration, "all discharged", current)
        repaired = agent.repair(current, build(imported, checked))
        if repaired is None:
            return LoopOutcome(False, iteration, "agent gave up", current)
        if repaired == current:
            return LoopOutcome(False, iteration, "fixed point", current)
        current = repaired
    return LoopOutcome(False, max_iterations, "budget exhausted", current)
