"""R2 enforcement hook: spec translation must preserve strength (draft §5.4 R2).

API only in M1 - the full cross-artifact translator lands in M4. Semantics of the
hook (aligned with the plan's R2 wording):

- Every source `ensures`/`invariants` clause must have a syntactic
  (shared-theory) counterpart in the lowered spec. A missing counterpart means
  the target proves less than the source claimed -> `soundness_discipline="lossy"`
  and an open residual I4 obligation per missing clause (deterministic content,
  so `emit_residual_obligations` reproduces exactly the ids recorded in the
  translation's residuals).
- Adding a `requires` clause to the lowered spec **weakens the specification**
  (it restricts the inputs the contract covers). Per draft §5.4 that is a hard
  error: `SpecWeakeningError`, not a marker.
- If every clause is preserved, the discipline is `shadow-validated` (the
  strength check itself is the shadow evidence available in M1).
"""

from __future__ import annotations

from ...artifacts import (
    Obligation,
    Specification,
    Translation,
    artifact_id,
    canonical_json_bytes,
)
from ...artifacts.obligation import Sequent
from ...artifacts.terms import Term
from ...artifacts.translation import Residuals, SoundnessDiscipline

_WEAKENING_MESSAGE = "spec weakening detected: lowering adds requires clauses"


class SpecWeakeningError(Exception):
    pass


def _canonical(term: Term) -> str:
    return canonical_json_bytes(term.model_dump(mode="json")).decode()


def _has_counterpart(term: Term, pool: list[Term]) -> bool:
    key = _canonical(term)
    return any(_canonical(other) == key for other in pool)


def _missing_clauses(source_clauses: list[Term], target_clauses: list[Term]) -> list[Term]:
    return [c for c in source_clauses if not _has_counterpart(c, target_clauses)]


def _added_requires(source: Specification, lowered: Specification) -> list[Term]:
    return _missing_clauses(lowered.contracts.requires, source.contracts.requires)


def check_spec_strength(source: Specification, lowered: Specification) -> Translation:
    """Assert source contract strength survives the lowering; R2 enforcement."""
    added = _added_requires(source, lowered)
    if added:
        rendered = "; ".join(_canonical(t) for t in added)
        raise SpecWeakeningError(f"{_WEAKENING_MESSAGE}: {rendered}")

    missing_ensures = _missing_clauses(source.contracts.ensures, lowered.contracts.ensures)
    missing_invariants = _missing_clauses(source.contracts.invariants, lowered.contracts.invariants)
    residuals = missing_ensures + missing_invariants

    if residuals:
        discipline: SoundnessDiscipline = "lossy"
    else:
        discipline = "shadow-validated"

    return Translation(
        source_artifact=artifact_id(source),
        target_artifact=artifact_id(lowered),
        source_kind="specification",
        target_kind="specification",
        mapping=[
            {"source_slot": slot, "target_slot": slot, "kind": "contract-clause"}
            for slot in ("requires", "ensures", "modifies", "invariants")
        ],
        soundness_discipline=discipline,
        residuals=Residuals(
            assumptions_added=[],
            dropped_fragments=[],
            residual_obligations=[
                artifact_id(o) for o in emit_residual_obligations(source, lowered)
            ],
        ),
        notes=(
            "R2 strength check (M1 hook): missing clause counterparts become open "
            "residual obligations (reproducible via emit_residual_obligations); "
            "added requires clauses raise SpecWeakeningError."
        ),
    )


def emit_residual_obligations(source: Specification, lowered: Specification) -> list[Obligation]:
    """Open I4 obligations for every missing clause counterpart (deterministic)."""
    pairs: tuple[tuple[str, list[Term], list[Term]], ...] = (
        ("ensures", source.contracts.ensures, lowered.contracts.ensures),
        ("invariants", source.contracts.invariants, lowered.contracts.invariants),
    )
    obligations: list[Obligation] = []
    for _label, source_clauses, target_clauses in pairs:
        for clause in _missing_clauses(source_clauses, target_clauses):
            obligations.append(
                Obligation(
                    spec_ref=artifact_id(source),
                    program_ref=artifact_id(lowered),
                    semantics_model=lowered.semantics_model,
                    sequent=Sequent(context=[], goal=clause),
                    theories=lowered.theories,
                    target_profile=lowered.profile,
                    status="open",
                    origin_backend="r2-hook",
                )
            )
    return obligations
