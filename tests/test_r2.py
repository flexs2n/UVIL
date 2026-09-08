from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures import make_obligation
from uvil.adapters.smt.cex import build_counterexample, parse_model_valuation
from uvil.adapters.smt.r2 import (
    SpecWeakeningError,
    check_spec_strength,
    emit_residual_obligations,
)
from uvil.artifacts import Specification, artifact_id
from uvil.artifacts.spec import Contracts
from uvil.artifacts.terms import Term, const, t_eq, t_ge, t_le, var


def test_parse_model_valuation_scalars() -> None:
    model = (
        "(model\n  (define-fun x () Int\n    3)\n"
        "  (define-fun b () Bool\n    true)\n  (define-fun r () Real\n    2.5)\n)"
    )
    valuation = parse_model_valuation(model)
    assert valuation["x"].op == "const" and valuation["x"].args[0] == 3
    assert valuation["b"].op == "const" and valuation["b"].args[0] is True
    assert valuation["r"].op == "const" and valuation["r"].args[0] == 2.5


def test_parse_model_valuation_cvc5_style() -> None:
    model = "(\n  (define-fun x () Int 7)\n)"
    assert parse_model_valuation(model)["x"].args[0] == 7


def test_non_scalar_values_stay_out_of_valuation() -> None:
    model = (
        "((define-fun a () (Array Int Int) ((as const (Array Int Int)) 0)) (define-fun x () Int 1))"
    )
    valuation = parse_model_valuation(model)
    assert set(valuation) == {"x"}


def test_build_counterexample_snapshot(snapshot: SnapshotAssertion) -> None:
    cex = build_counterexample(
        make_obligation(), "((define-fun len () Int 3) (define-fun cap () Int 2))"
    )
    assert cex.kind == "valuation"
    assert cex.shared_render.smt_lib_valuation is not None
    assert cex.shared_render.human_summary.startswith("[unverified")
    assert cex.model_dump(mode="json") == snapshot


# -- R2 hook -----------------------------------------------------------------

INT = ["uvil.core.int@1"]


def _spec(ensures: list[Term], requires: list[Term] | None = None) -> Specification:
    return Specification(
        profile="uvil.boogie@1",
        theories=INT,
        semantics_model="model:why3-memory.v1",
        subject="p",
        contracts=Contracts(requires=requires or [], ensures=ensures),
    )


def test_r2_preserved_is_shadow_validated() -> None:
    source = _spec([t_ge(var("y"), const(0))])
    lowered = _spec([t_ge(var("y"), const(0))])
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "shadow-validated"
    assert translation.residuals.residual_obligations == []


def test_r2_missing_ensures_is_lossy_with_residual_i4() -> None:
    source = _spec([t_ge(var("y"), const(0)), t_le(var("y"), const(10))])
    lowered = _spec([t_ge(var("y"), const(0))])
    translation = check_spec_strength(source, lowered)
    assert translation.soundness_discipline == "lossy"
    residuals = emit_residual_obligations(source, lowered)
    assert len(residuals) == 1
    assert residuals[0].status == "open"
    assert residuals[0].origin_backend == "r2-hook"
    # ids recorded in the translation reproduce deterministically
    assert translation.residuals.residual_obligations == [artifact_id(residuals[0])]


def test_r2_added_requires_is_hard_error() -> None:
    source = _spec([t_ge(var("y"), const(0))])
    lowered = _spec([t_ge(var("y"), const(0))], requires=[t_eq(var("x"), const(0))])
    with pytest.raises(SpecWeakeningError, match="requires"):
        check_spec_strength(source, lowered)
