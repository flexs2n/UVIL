"""I2 - Specification: typed contract bundle over the core assertion language.

Core language = SMT-LIB v2 core-theory subset + `Opaque(ty, axiom_id)` escape hatch.
Contracts (`requires/ensures/modifies/decreases/invariant`), an LTL/TLA-style temporal
slot, and a per-assertion semantics-model reference. Also carries the shadow set
(R4): counter-hypotheses / test oracles so vacuity and faithfulness travel with
the artifact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .base import Artifact
from .terms import Term


class Contracts(BaseModel):
    requires: list[Term] = []
    ensures: list[Term] = []
    modifies: list[str] = []
    decreases: Term | None = None
    invariants: list[Term] = []


class TemporalFormula(BaseModel):
    kind: Literal["ltl", "tla"]
    formula: str


class OpaqueAxiom(BaseModel):
    ty: str
    axiom_id: str
    statement: str | None = None


class ShadowHypothesis(BaseModel):
    name: str
    formula: Term
    expect: Literal["refute", "accept"]


class Specification(Artifact):
    uvil_type = "specification"

    intent_ref: str | None = None
    profile: str = "uvil.core@1"
    theories: list[str] = Field(min_length=1)
    semantics_model: str
    subject: str
    contracts: Contracts = Contracts()
    temporal: list[TemporalFormula] = []
    opaque_axioms: list[OpaqueAxiom] = []
    shadows: list[ShadowHypothesis] = []
