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

M5 upgrade: syntactically-unmatched clauses are no longer automatically
missing - they go through `strength.check_spec_strength_semantic`, an SMT
implication probe over the LIA shared-theory subset (z3 settles `unsat` ⇒
preserved, `sat` ⇒ missing, `unknown`/timeout ⇒ conservative lossy + residual,
never silently passed). Added `requires` clauses remain a hard
`SpecWeakeningError` unless the source provably implies them.
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
    """Assert source contract strength survives the lowering; R2 enforcement.

    M5 dispatch: the syntactic fast path (canonical clause match, zero solver
    calls) returns immediately; only syntactically-unmatched clauses go to the
    semantic LIA probe (`strength.check_spec_strength_semantic`), which accepts
    syntactically-different-but-equivalent clauses and conservatively downgrades
    anything the probe cannot settle.
    """
    from .strength import check_spec_strength_semantic

    if (
        not _added_requires(source, lowered)
        and not _missing_clauses(source.contracts.ensures, lowered.contracts.ensures)
        and not _missing_clauses(source.contracts.invariants, lowered.contracts.invariants)
    ):
        return _strength_translation(
            source,
            lowered,
            missing_ensures=[],
            missing_invariants=[],
            dropped_notes=[],
            semantic=False,
        )
    return check_spec_strength_semantic(source, lowered)


def _strength_translation(
    source: Specification,
    lowered: Specification,
    *,
    missing_ensures: list[Term],
    missing_invariants: list[Term],
    dropped_notes: list[str],
    semantic: bool,
) -> Translation:
    residuals = missing_ensures + missing_invariants
    if residuals or dropped_notes:
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
            dropped_fragments=dropped_notes,
            residual_obligations=[
                artifact_id(o)
                for o in emit_residual_obligations(
                    source,
                    lowered,
                    missing_ensures=missing_ensures,
                    missing_invariants=missing_invariants,
                )
            ],
        ),
        notes=(
            "R2 strength check ("
            + ("M5 semantic LIA probe" if semantic else "M1 hook")
            + "): missing clause counterparts become open "
            "residual obligations (reproducible via emit_residual_obligations); "
            "added requires clauses raise SpecWeakeningError."
        ),
    )


def emit_residual_obligations(
    source: Specification,
    lowered: Specification,
    missing_ensures: list[Term] | None = None,
    missing_invariants: list[Term] | None = None,
) -> list[Obligation]:
    """Open I4 obligations for every missing clause counterpart (deterministic).

    The missing-clause lists default to the syntactic counterparts; the M5
    semantic path passes its probe-determined lists explicitly (same
    obligation shape, so ids stay reproducible from the clause lists).
    """
    if missing_ensures is None:
        missing_ensures = _missing_clauses(source.contracts.ensures, lowered.contracts.ensures)
    if missing_invariants is None:
        missing_invariants = _missing_clauses(
            source.contracts.invariants, lowered.contracts.invariants
        )
    pairs: tuple[tuple[str, list[Term]], ...] = (
        ("ensures", missing_ensures),
        ("invariants", missing_invariants),
    )
    obligations: list[Obligation] = []
    for _label, missing in pairs:
        for clause in missing:
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
