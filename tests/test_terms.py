from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures import make_obligation, vec_goal_term
from uvil.artifacts import Obligation
from uvil.artifacts import terms as T
from uvil.artifacts.terms import to_smt


def test_canonical_bytes_snapshot(obligation: Obligation, snapshot: SnapshotAssertion) -> None:
    from uvil.artifacts import canonical_bytes

    assert canonical_bytes(obligation).decode() == snapshot


@pytest.fixture
def obligation() -> Obligation:
    return make_obligation()


def test_var() -> None:
    assert to_smt(T.var("x")) == "x"


def test_const_bool() -> None:
    assert to_smt(T.const(True)) == "true"
    assert to_smt(T.const(False)) == "false"


def test_const_int() -> None:
    assert to_smt(T.const(42)) == "42"


def test_const_real_whole() -> None:
    assert to_smt(T.const(1.0)) == "1.0"


def test_core_ops() -> None:
    x, y = T.var("x"), T.var("y")
    assert to_smt(T.t_and(x, y)) == "(and x y)"
    assert to_smt(T.t_implies(x, y)) == "(=> x y)"
    assert to_smt(T.t_eq(x, y)) == "(= x y)"
    assert to_smt(T.t_neq(x, y)) == "(distinct x y)"
    assert to_smt(T.t_le(x, y)) == "(<= x y)"
    assert to_smt(T.t_add(x, y, x)) == "(+ x y x)"
    assert to_smt(T.t_sub(x, y)) == "(- x y)"
    assert to_smt(T.t_ite(x, y, T.const(0))) == "(ite x y 0)"
    assert to_smt(T.t_select(x, y)) == "(select x y)"
    assert to_smt(T.t_store(x, y, T.const(1))) == "(store x y 1)"


def test_quantifiers() -> None:
    body = T.t_ge(T.t_add(T.var("i"), T.const(1)), T.const(0))
    assert to_smt(T.t_forall("i", "Int", body)) == "(forall ((i Int)) (>= (+ i 1) 0))"
    assert to_smt(T.t_exists("i", "Int", body)) == "(exists ((i Int)) (>= (+ i 1) 0))"


def test_seq_ops() -> None:
    s = T.var("s")
    assert to_smt(T.Term(op="seq.len", args=[s])) == "(seq.len s)"


def test_opaque_has_no_rendering() -> None:
    with pytest.raises(ValueError, match="opaque"):
        to_smt(T.opaque("FractionalPerm", "axiom-42"))


def test_unknown_op_rejected() -> None:
    with pytest.raises(ValueError, match="unknown core operator"):
        to_smt(T.Term(op="frobnicate", args=[]))


def test_vec_goal_terms() -> None:
    assert to_smt(vec_goal_term()) == "(= (- cap len) 0)"


def test_obligation_sequent_defaults(obligation: Obligation) -> None:
    assert obligation.status == "open"
    assert obligation.sequent.context != []
