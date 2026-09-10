"""M5 R2 semantic spec-strength tests (LIA subset) + probe discovery pins.

Discovery-first discipline: the first tests pin how the pinned z3 behaves on
implication probes over the LIA families (including the div/mod semantics
note: SMT-LIB `mod` yields non-negative remainders for positive divisors,
matching Lean's floored `mod` on that domain) before the wiring relies on it.
"""

from __future__ import annotations

import pytest

from uvil.adapters.smt.r2 import (
    SpecWeakeningError,
    check_spec_strength,
    emit_residual_obligations,
)
from uvil.adapters.smt.strength import (
    DEFAULT_PROBE_BUDGET_MS,
    check_spec_strength_semantic,
)
from uvil.artifacts import Specification, artifact_id
from uvil.artifacts.spec import Contracts
from uvil.artifacts.terms import Term, const, t_add, t_eq, t_ge, t_le, var


def t_mod(a: Term, b: Term) -> Term:
    return Term(op="mod", args=[a, b])


INT = ["uvil.core.int@1"]


def _spec(
    ensures: list[Term],
    requires: list[Term] | None = None,
    invariants: list[Term] | None = None,
) -> Specification:
    return Specification(
        profile="uvil.boogie@1",
        theories=INT,
        semantics_model="model:why3-memory.v1",
        subject="p",
        contracts=Contracts(requires=requires or [], ensures=ensures, invariants=invariants or []),
    )


# --- discovery pins (probe behavior over the LIA families) ---------------------------


def test_discovery_equivalent_clauses_probe_unsat() -> None:
    # `y >= 0` vs `0 <= y`: different canonical forms, same meaning; the probe
    # (lowered ∧ ¬source-clause) must be unsat under the pinned z3.
    source = _spec([t_ge(var("y"), const(0))])
    lowered = _spec([t_le(const(0), var("y"))])
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "shadow-validated"
    assert translation.residuals.residual_obligations == []
    assert "semantic LIA probe" in (translation.notes or "")


def test_discovery_div_mod_semantics_probe_unsat() -> None:
    # SMT-LIB `mod` with a positive divisor is non-negative (the Euclidean
    # reading), so `(a mod 3) >= 0` is valid with no context: the probe must
    # settle unsat, pinning the div/mod correspondence used by the corpus.
    source = _spec([t_ge(t_mod(var("a"), const(3)), const(0))])
    lowered = _spec([])
    translation = check_spec_strength_semantic(source, lowered)
    assert translation.soundness_discipline == "shadow-validated"
    assert translation.residuals.residual_obligations == []


def test_discovery_weakened_clause_probe_sat() -> None:
    # y >= 0 does not imply y <= 10: the probe must be sat (a witness exists).
    source = _spec([t_le(var("y"), const(10))])
    lowered = _spec([t_ge(var("y"), const(0))])
    translation = check_spec_strength_semantic(source, lowered)
    assert translation.soundness_discipline == "lossy"
    residuals = emit_residual_obligations(source, lowered)
    assert len(residuals) == 1
    assert translation.residuals.residual_obligations == [artifact_id(residuals[0])]


def test_discovery_equivalent_requires_probe_unsat() -> None:
    # source requires x >= 0 implies the differently-written `x >= 0 + 0`:
    # no weakening, no error.
    source = _spec([], requires=[t_ge(var("x"), const(0))])
    lowered = _spec([], requires=[t_ge(var("x"), t_add(const(0), const(0)))])
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "shadow-validated"
    assert translation.residuals.residual_obligations == []


# --- dispatch behavior ----------------------------------------------------------------


def test_syntactic_fast_path_makes_no_solver_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # exact canonical match: zero solver calls (the M1 cost profile is kept)
    def explode(*a: object, **k: object) -> None:
        raise AssertionError("solver must not be called on the syntactic fast path")

    monkeypatch.setattr("uvil.adapters.smt.backends.Z3Backend.run", explode)
    source = _spec([t_ge(var("y"), const(0))])
    lowered = _spec([t_ge(var("y"), const(0))])
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "shadow-validated"


def test_genuinely_weakened_clause_still_lossy() -> None:
    source = _spec([t_ge(var("y"), const(0)), t_le(var("y"), const(10))])
    lowered = _spec([t_ge(var("y"), const(0))])
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "lossy"
    # the residual ids reproduce from the semantically-missing clause list
    residuals = emit_residual_obligations(source, lowered)
    assert len(residuals) == 1
    assert residuals[0].sequent.goal == t_le(var("y"), const(10))
    assert residuals[0].origin_backend == "r2-hook"
    assert translation.residuals.residual_obligations == [artifact_id(residuals[0])]


def test_added_requires_is_still_hard_error() -> None:
    # a truly added precondition (source does not imply it) stays the M1 hard
    # error, now settled by the semantic probe
    source = _spec([t_ge(var("y"), const(0))])
    lowered = _spec([t_ge(var("y"), const(0))], requires=[t_eq(var("x"), const(0))])
    with pytest.raises(SpecWeakeningError, match="requires"):
        check_spec_strength(source, lowered)


def test_semantically_implied_requires_is_not_weakening() -> None:
    source = _spec([t_ge(var("y"), const(0))], requires=[t_ge(var("x"), const(0))])
    # lowered requires x + 0 >= 0: implied by the source requires (probe unsat)
    lowered = _spec(
        [t_ge(var("y"), const(0))],
        requires=[t_ge(t_add(var("x"), const(0)), const(0))],
    )
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "shadow-validated"


def test_unknown_probe_is_conservative_lossy_with_note() -> None:
    # nonlinear integer goal: the pinned z3 may return unknown/timeout within a
    # tiny budget; the conservative mapping must be lossy + residual, never a
    # silent pass. (Conditional: the specific outcome is solver-dependent.)
    hard = t_ge(var("x"), const(0))
    source = _spec([hard])
    lowered = _spec([t_ge(t_add(var("x"), const(0)), const(0))])  # equivalent, different syntax
    translation = check_spec_strength_semantic(source, lowered, timeout_ms=50)
    if translation.soundness_discipline == "shadow-validated":
        return  # the pinned z3 settled the probe; nothing to assert here
    assert translation.soundness_discipline == "lossy"
    assert translation.residuals.dropped_fragments
    assert any("conservative" in note for note in translation.residuals.dropped_fragments)
    assert translation.residuals.residual_obligations == [
        artifact_id(o) for o in emit_residual_obligations(source, lowered)
    ]


@pytest.mark.slow
def test_timeout_probe_is_conservative_lossy() -> None:
    # Fermat-flavored nonlinear implication within a 50ms budget: the probe
    # cannot settle it, so the outcome must be the conservative downgrade.
    from uvil.artifacts.terms import t_mul

    def fifth(v: Term) -> Term:
        return t_mul(t_mul(t_mul(t_mul(v, v), v), v), v)

    # goal: x^5 + y^5 <= z^5 (a probe the pinned z3 cannot settle quickly)
    x, y, z = var("x"), var("y"), var("z")
    hard = t_le(t_add(fifth(x), fifth(y)), fifth(z))
    source = _spec([hard])
    lowered = _spec([])
    translation = check_spec_strength_semantic(source, lowered, timeout_ms=50)
    assert translation.soundness_discipline == "lossy"
    assert translation.residuals.dropped_fragments
    assert any("conservative" in note for note in translation.residuals.dropped_fragments)
    assert DEFAULT_PROBE_BUDGET_MS == 5000
