"""Lean encoder tests: golden theorem snapshots + fail-loud unsupported terms.

No Lean toolchain required - these run everywhere (the live-discovery half of
the M3 pair lives in `test_lean_discovery.py`).
"""

from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures import make_obligation
from uvil.adapters.boogie.lower import import_module
from uvil.adapters.lean.encode import (
    UnsupportedTermError,
    theorem_name,
    to_lean_theorem,
)
from uvil.artifacts import Obligation
from uvil.artifacts.terms import (
    Term,
    const,
    t_add,
    t_and,
    t_eq,
    t_exists,
    t_forall,
    t_ge,
    t_gt,
    t_implies,
    t_ite,
    t_le,
    t_lt,
    t_mul,
    t_neq,
    t_not,
    t_or,
    t_sub,
    var,
)


def _obligation_with_goal(
    goal: Term,
    context: list[Term] | None = None,
    var_sorts: dict[str, str] | None = None,
) -> Obligation:
    data = make_obligation().model_dump()
    data["sequent"]["goal"] = goal.model_dump(mode="json")
    if context is not None:
        data["sequent"]["context"] = [t.model_dump(mode="json") for t in context]
    if var_sorts is not None:
        data["sequent"]["var_sorts"] = var_sorts
    return Obligation.model_validate(data)


# --- golden theorem snapshots ---------------------------------------------------


def test_golden_fixture_obligation(snapshot: SnapshotAssertion) -> None:
    (text,) = [to_lean_theorem(make_obligation())]
    assert text == snapshot


@pytest.mark.parametrize(
    "goal,var_sorts",
    [
        (t_eq(t_add(var("x"), const(1)), var("cap")), {}),
        (t_and(t_or(var("p"), var("q")), t_not(var("p"))), {"p": "Bool", "q": "Bool"}),
        (t_implies(t_ge(var("x"), const(0)), t_neq(var("y"), const(3))), {}),
        (t_lt(t_sub(var("x"), var("y")), const(-2)), {}),
        (
            t_forall("i", "Int", t_le(t_add(var("i"), const(1)), var("n"))),
            {"n": "Int"},
        ),
        (t_exists("j", "Int", t_eq(t_add(var("j"), var("n")), const(0))), {"n": "Int"}),
        (t_eq(t_ite(t_lt(var("x"), const(0)), t_mul(const(2), var("x")), var("x")), const(5)), {}),
        (t_not(t_or(t_le(var("x"), const(0)), t_gt(var("x"), const(9)))), {}),
    ],
    ids=[
        "arith",
        "bool-props",
        "implies-neq",
        "negative-const",
        "forall",
        "exists",
        "ite-mul",
        "not-or",
    ],
)
def test_golden_theorem_per_shape(
    goal: Term, var_sorts: dict[str, str], snapshot: SnapshotAssertion
) -> None:
    assert to_lean_theorem(_obligation_with_goal(goal, var_sorts=var_sorts)) == snapshot


def test_golden_theorem_name_is_stable_12hex() -> None:
    obl = make_obligation()
    name = theorem_name(obl)
    assert name.startswith("uvil_obl_")
    digest = name.removeprefix("uvil_obl_")
    assert len(digest) == 12
    assert all(c in "0123456789abcdef" for c in digest)
    assert theorem_name(make_obligation()) == name


# --- div/mod: constant-pin propagation -------------------------------------------


def test_divmod_corpus_family_encodes_via_pin_propagation(snapshot: SnapshotAssertion) -> None:
    result = import_module(
        "procedure p(a: int, b: int)\n  requires b == 7\n{\n  assert a / b * b + a % b == a;\n}\n",
        "dm.bpl",
    )
    assert result.ok, [d.native_message for d in result.diagnostics]
    (obl,) = result.obligations
    theorem = to_lean_theorem(obl)
    assert "/ 7" in theorem and "% 7" in theorem
    assert theorem == snapshot


def test_nonpositive_divisor_fails_loud() -> None:
    # variable divisor (no pin) and negative/zero literals all fail loud
    cases = [
        t_eq(Term(op="intdiv", args=[var("a"), var("b")]), const(1)),
        t_ge(Term(op="intdiv", args=[var("a"), const(0)]), const(1)),
        t_ge(Term(op="mod", args=[var("a"), const(-3)]), const(0)),
    ]
    for goal in cases:
        with pytest.raises(UnsupportedTermError, match="positive constant divisor"):
            to_lean_theorem(_obligation_with_goal(goal))


def test_pin_propagation_honors_quantifier_shadowing() -> None:
    # a bound `b` inside the goal must not pick up the outer pin: the context
    # equality degenerates to `5 = 5`, the quantifier body stays `1 * b = b`
    goal = t_forall("b", "Int", t_eq(t_mul(const(1), var("b")), var("b")))
    context = [t_eq(var("b"), const(5))]
    theorem = to_lean_theorem(_obligation_with_goal(goal, context))
    assert "(5 = 5)" in theorem
    assert "∀ b : Int, ((1 * b) = b)" in theorem
    assert "b = 5" not in theorem and "5 = b" not in theorem


# --- fail loud (R3): unsupported subset -------------------------------------------


def _unsupported_sort_obligation(sort: str) -> Obligation:
    data = make_obligation().model_dump()
    data["sequent"]["var_sorts"]["cap"] = sort
    return Obligation.model_validate(data)


@pytest.mark.parametrize("sort", ["Real", "(Array Int Int)", "(Seq Int)"])
def test_unsupported_var_sorts_fail_loud(sort: str) -> None:
    with pytest.raises(UnsupportedTermError, match="unsupported sort"):
        to_lean_theorem(_unsupported_sort_obligation(sort))


def test_opaque_term_fails_loud_with_verbatim_fragment() -> None:
    data = make_obligation().model_dump()
    data["sequent"]["goal"] = Term(op="opaque", args=["FractionalPerm", "ax-1"]).model_dump(
        mode="json"
    )
    with pytest.raises(UnsupportedTermError) as e:
        to_lean_theorem(Obligation.model_validate(data))
    # opaque has no SMT rendering either: the structural repr IS the verbatim
    # fragment, and it round-trips the ty/axiom identifiers
    assert "opaque" in e.value.native_message
    assert "FractionalPerm" in e.value.native_message
    assert "ax-1" in e.value.native_message


def test_nonlinear_mul_fails_loud() -> None:
    goal = t_eq(t_mul(var("x"), var("x")), t_add(t_mul(var("y"), const(2)), const(1)))
    with pytest.raises(UnsupportedTermError, match="nonlinear"):
        to_lean_theorem(_obligation_with_goal(goal))


def test_real_const_fails_loud() -> None:
    with pytest.raises(UnsupportedTermError, match="Real"):
        to_lean_theorem(_obligation_with_goal(t_eq(var("x"), const(2.5))))


def test_bool_bool_equality_fails_loud() -> None:
    goal = t_implies(t_ge(var("x"), const(0)), t_eq(var("p"), var("q")))
    with pytest.raises(UnsupportedTermError, match="Bool"):
        to_lean_theorem(
            _obligation_with_goal(goal, var_sorts={"p": "Bool", "q": "Bool", "x": "Int"})
        )


def test_bool_ordering_fails_loud() -> None:
    goal = t_lt(var("p"), var("q"))
    with pytest.raises(UnsupportedTermError, match="Bool"):
        to_lean_theorem(_obligation_with_goal(goal, var_sorts={"p": "Bool", "q": "Bool"}))


def test_seq_and_array_ops_fail_loud() -> None:
    seq_goal = t_ge(Term(op="seq.len", args=[var("s")]), const(1))
    with pytest.raises(UnsupportedTermError, match=r"seq\.len|unsupported sort"):
        to_lean_theorem(_obligation_with_goal(seq_goal, var_sorts={"s": "(Seq Int)"}))
    arr_goal = t_eq(Term(op="select", args=[var("arr"), const(1)]), const(2))
    with pytest.raises(UnsupportedTermError, match="unsupported sort"):
        to_lean_theorem(_obligation_with_goal(arr_goal, var_sorts={"arr": "(Array Int Int)"}))


def test_unsupported_error_carries_verbatim_sexpr() -> None:
    goal = t_mul(var("x"), var("y"))
    with pytest.raises(UnsupportedTermError) as e:
        to_lean_theorem(_obligation_with_goal(goal))
    assert "(* x y)" in e.value.native_message
