from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures import make_obligation
from uvil.adapters.smt.encode import (
    OpaqueTermError,
    encode_assertions,
    encode_script,
)
from uvil.artifacts import Obligation
from uvil.artifacts.terms import Term


@pytest.fixture
def obligation() -> Obligation:
    return make_obligation()


def test_encode_assertions_snapshot(obligation: Obligation, snapshot: SnapshotAssertion) -> None:
    assert encode_assertions(obligation) == snapshot


def test_encode_script_has_commands(obligation: Obligation) -> None:
    script = encode_script(obligation)
    assert script.startswith("(set-logic ALL)")
    assert "(check-sat)" in script
    assert "(get-model)" in script
    assert "(get-info :version)" in script
    assert script.count("(assert") == len(obligation.sequent.context) + 1


def test_goal_is_negated(obligation: Obligation) -> None:
    text = encode_assertions(obligation)
    assert "(assert (not" in text


def test_var_sorts_become_declarations(obligation: Obligation) -> None:
    text = encode_assertions(obligation)
    assert "(declare-const cap Int)" in text
    assert "(declare-const len Int)" in text


def test_unknown_sort_defaults_to_int() -> None:
    data = make_obligation().model_dump()
    data["sequent"]["var_sorts"] = {}
    rebuilt = Obligation.model_validate(data)
    text = encode_assertions(rebuilt)
    assert "(declare-const cap Int)" in text


def test_opaque_term_surfaces_error() -> None:
    data = make_obligation().model_dump()
    data["sequent"]["goal"] = Term(op="opaque", args=["FractionalPerm", "axiom-42"]).model_dump(
        mode="json"
    )
    rebuilt = Obligation.model_validate(data)
    with pytest.raises(OpaqueTermError) as e:
        encode_assertions(rebuilt)
    assert "opaque" in e.value.native_message
