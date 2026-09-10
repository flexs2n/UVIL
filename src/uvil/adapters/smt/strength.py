"""R2 spec-strength checking, semantic arm: LIA clause-preservation probes.

The M1 R2 hook (`r2.py`) matched clauses by canonical-JSON equality - sound but
blind to syntactically-different-but-equivalent clauses (its documented
false-negative family). This module adds the semantic probe for the LIA
shared-theory subset (the user-locked M5 scope; the arbitrary-spec translator
stays out of scope):

- A source `ensures`/`invariants` clause is preserved iff the lowered spec
  *implies* it over the source context: the probe
  `(source.requires ∧ source.invariants ∧ target-ensures ∧ target-invariants) ∧ ¬clause`
  must be **unsat**.
- An "added" `requires` clause (no syntactic counterpart) only weakens the
  spec if the source does NOT imply it: probe
  `(source.requires ∧ source.invariants) ∧ ¬clause`. `sat` (or an
  inconclusive probe) ⇒ `SpecWeakeningError` - the hard error is unchanged.

Probe outcomes are total and fail loud:
- `unsat`  ⇒ clause preserved (zero residual).
- `sat`    ⇒ weakened/missing ⇒ `lossy` + deterministic residual obligation.
- `unknown`/`timeout` ⇒ conservative `lossy` + residual, with the probe
  outcome recorded in `residuals.dropped_fragments` - an inconclusive probe is
  never silently passed.

Div/mod note (pinned by the discovery test): the SMT-LIB `mod` on Int yields
non-negative remainders for positive divisors, matching Lean's floored `mod`
on that domain - implication probes over the corpus div/mod families are
therefore settled by the pinned z3, not by an axiom patch.
"""

from __future__ import annotations

from typing import Literal

from ...artifacts import Obligation, Specification, Translation, artifact_id
from ...artifacts.obligation import CostBudget, Sequent
from ...artifacts.terms import Term
from ...check.core import SmtBackend
from .backends import SmtVerdict
from .encode import OpaqueTermError
from .r2 import (
    _WEAKENING_MESSAGE,
    SpecWeakeningError,
    _added_requires,
    _canonical,
    _missing_clauses,
    _strength_translation,
)

DEFAULT_PROBE_BUDGET_MS = 5000

PROBE_BACKEND_TAG = "r2-semantic-probe"

ProbeOutcome = Literal["preserved", "missing", "unknown", "timeout"]


def _probe_obligation(
    source: Specification, lowered: Specification, context: list[Term], clause: Term
) -> Obligation:
    """Build the implication probe as a validity question `context ⊢ clause`.

    The SMT encoder asserts `(not goal)`, so `unsat` means the implication
    holds and `sat` means a counterexample valuation exists.
    """
    return Obligation(
        spec_ref=artifact_id(source),
        program_ref=artifact_id(lowered),
        semantics_model=lowered.semantics_model,
        sequent=Sequent(context=context, goal=clause),
        theories=lowered.theories,
        target_profile=lowered.profile,
        status="open",
        cost_budget=CostBudget(solver_ms=DEFAULT_PROBE_BUDGET_MS),
        origin_backend=PROBE_BACKEND_TAG,
    )


def _run_probe(
    engine: SmtBackend,
    source: Specification,
    lowered: Specification,
    context: list[Term],
    clause: Term,
    timeout_ms: int,
) -> tuple[ProbeOutcome, SmtVerdict | None, str | None]:
    """Run one implication probe; total, never raises for solver outcomes."""
    obl = _probe_obligation(source, lowered, context, clause)
    try:
        verdict = engine.run(obl, timeout_ms)
    except (OpaqueTermError, ValueError) as e:
        # An unencodable clause has no semantic probe: conservative missing.
        return "unknown", None, getattr(e, "native_message", None) or str(e)
    if verdict.status == "unsat":
        return "preserved", verdict, None
    if verdict.status == "sat":
        return "missing", verdict, None
    return "unknown" if verdict.status == "unknown" else "timeout", verdict, None


def check_spec_strength_semantic(
    source: Specification,
    lowered: Specification,
    timeout_ms: int = DEFAULT_PROBE_BUDGET_MS,
    backend: str = "z3",
) -> Translation:
    """Semantic clause-preservation check over the LIA subset (R2, M5)."""
    engine = SmtBackend(backend)

    # requires: the source must imply every lowered precondition; otherwise
    # the lowering adds preconditions = weakening = hard error (M1 semantics,
    # now settled semantically instead of only syntactically).
    added_syntactic = _added_requires(source, lowered)
    for clause in added_syntactic:
        outcome, _verdict, detail = _run_probe(
            engine,
            source,
            lowered,
            [*source.contracts.requires, *source.contracts.invariants],
            clause,
            timeout_ms,
        )
        if outcome != "preserved":
            rendered = "; ".join(_canonical(t) for t in added_syntactic)
            suffix = f" (probe {outcome}: {detail})" if detail else f" (probe {outcome})"
            raise SpecWeakeningError(f"{_WEAKENING_MESSAGE}: {rendered}{suffix}")

    # ensures/invariants: the lowered spec must imply every source clause.
    missing_ensures: list[Term] = []
    missing_invariants: list[Term] = []
    dropped_notes: list[str] = []
    probe_context = [
        *source.contracts.requires,
        *source.contracts.invariants,
        *lowered.contracts.ensures,
        *lowered.contracts.invariants,
    ]
    slots: tuple[tuple[str, list[Term], list[Term], list[Term]], ...] = (
        ("ensures", source.contracts.ensures, lowered.contracts.ensures, missing_ensures),
        (
            "invariants",
            source.contracts.invariants,
            lowered.contracts.invariants,
            missing_invariants,
        ),
    )
    for _label, source_clauses, target_clauses, sink in slots:
        for clause in _missing_clauses(source_clauses, target_clauses):
            outcome, _verdict, detail = _run_probe(
                engine, source, lowered, probe_context, clause, timeout_ms
            )
            if outcome == "preserved":
                continue
            sink.append(clause)
            if outcome in ("unknown", "timeout"):
                dropped_notes.append(
                    f"semantic probe returned {outcome} for clause "
                    f"{_canonical(clause)} (budget {timeout_ms}ms): conservative "
                    "residual, preservation unestablished"
                    + (f"; probe detail: {detail}" if detail else "")
                )

    return _strength_translation(
        source,
        lowered,
        missing_ensures=missing_ensures,
        missing_invariants=missing_invariants,
        dropped_notes=dropped_notes,
        semantic=True,
    )
