"""I4 - Obligation: the atomic unit of verification.

A sequent `Γ ⊢ φ` over the shared theories, plus originating program slice,
responsible backend profile, status, and cost metadata. Status ∈
{open, discharged, refuted, timeout, vacuous}.

Obligation identity (cache key for the M5 incremental protocol) is defined in
`uvil.store.identity` as a hash of
`(spec, semantics_model, program_fragment, profile_version)`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .base import Artifact
from .terms import Term

ObligationStatus = Literal["open", "discharged", "refuted", "timeout", "vacuous"]


class Sequent(BaseModel):
    context: list[Term] = []
    goal: Term
    # Name -> SMT-LIB sort for free variables of the sequent (e.g. {"x": "Int"}).
    # Empty means "unknown": SMT encoders must then default to Int and may
    # refuse boolean/collection variables. Populated by adapters that know the
    # source types (e.g. the Boogie importer).
    var_sorts: dict[str, str] = {}


class CostBudget(BaseModel):
    solver_ms: int | None = None
    kernel_ms: int | None = None


class Obligation(Artifact):
    uvil_type = "obligation"

    spec_ref: str
    program_ref: str
    semantics_model: str
    sequent: Sequent
    theories: list[str] = Field(min_length=1)
    target_profile: str
    status: ObligationStatus = "open"
    cost_budget: CostBudget = CostBudget()
    origin_backend: str | None = None
