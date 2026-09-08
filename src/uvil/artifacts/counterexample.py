"""I6 - Counterexample: standardized witness shapes.

Shapes: `Valuation` (SMT model → shared-theory terms), `Trace` (finite execution,
program state per step), `Scenario` (TLA+/TLC-style behavior), `CounterSpec`
(a spec-strengthening witness, e.g. an input exhibiting vacuity). Every shape is
renderable per-backend and to a common JSON form for agent consumption.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import Artifact
from .terms import Term

CounterexampleKind = Literal["valuation", "trace", "scenario", "counterspec"]


class SharedRender(BaseModel):
    smt_lib_valuation: str | None = None
    human_summary: str | None = None


class BackendWitness(BaseModel):
    format: str
    payload: Any = None


class TraceState(BaseModel):
    vars: dict[str, str] = {}
    loc: str | None = None


class Counterexample(Artifact):
    uvil_type = "counterexample"

    obligation_ref: str
    kind: CounterexampleKind
    valuation: dict[str, Term] | None = None
    trace: list[TraceState] | None = None
    scenario: list[TraceState] | None = None
    counter_spec: Term | None = None
    shared_render: SharedRender = Field(default_factory=SharedRender)
    backend_witness: BackendWitness | None = None
