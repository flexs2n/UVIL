from __future__ import annotations

import json

import pytest
from syrupy.assertion import SnapshotAssertion

from uvil.adapters.boogie.lower import import_module, term_vars
from uvil.adapters.boogie.parser import BoogieParseError, parse_module

FULL_MODULE = """
const MAX: int := 100;
axiom A1: MAX >= 0;
type T = int;
var g: int;

function abs(x: int) returns (int) {
  if x >= 0 then x else -x
}

procedure clamp(x: int) returns (y: int)
  requires x >= -100 && x <= 100
  ensures -100 <= y && y <= 100
  modifies g
{
  assume x <= 50;
  y := 0;
  assert abs(x) <= 100;
  havoc y;
  assert y >= -1000;
  assert y > 0 by {
    assume x >= 1;
  }
  while y < 10
    invariant y >= 0
  {
    y := y + 1;
  }
  assert y >= 0;
}

procedure arrays(a: [int]int) returns (b: [int]int)
  requires a[0] == 1
{
  b := a[0 := 7];
  assert a[5] == a[5];
}

procedure seqs(s: seq<int>)
  requires |s| >= 1
{
  assert s[0] == s[0];
}

procedure quantified(n: int)
  requires n >= 1
  requires forall i: int :: 0 <= i && i < n ==> i <= n
{
  assert forall j: int :: 0 <= j && j < n ==> j < n + 1;
}
"""


def test_module_parses() -> None:
    module = parse_module(FULL_MODULE)
    assert len(module.procedures) == 4
    assert module.consts[0].name == "MAX"
    assert module.type_aliases["T"].sort == "int"
    assert module.axioms[0].name == "A1"
    assert module.functions[0].name == "abs"


def test_import_obligation_counts() -> None:
    result = import_module(FULL_MODULE, "full.bpl")
    assert result.ok, [d.native_message for d in result.diagnostics]
    counts = {name: len(p.obligations) for name, p in result.procedures.items()}
    # clamp: 4 asserts + loop initiation + loop preservation (WP VCG)
    assert counts == {"clamp": 6, "arrays": 1, "seqs": 1, "quantified": 1}


def test_import_wp_markers_and_budget() -> None:
    result = import_module(FULL_MODULE, "full.bpl")
    obl = result.procedures["clamp"].obligations[0]
    assert obl.origin_backend == "boogie-wp"
    assert obl.target_profile == "uvil.boogie@1"
    assert obl.cost_budget.solver_ms == 2000
    assert result.procedures["clamp"].program.language == "boogie"
    assert result.procedures["clamp"].program.semantics_model == "model:why3-memory.v1"


def test_context_is_path_and_invariant_frames() -> None:
    result = import_module(FULL_MODULE, "full.bpl")
    clamps = result.procedures["clamp"].obligations

    def smt_goal(i: int) -> str:
        from uvil.artifacts import to_smt

        return to_smt(clamps[i].sequent.goal)

    # 1: function body inlined
    assert "(ite" in smt_goal(0)
    # 3: `assert ... by` context carries the block's assume
    ctx3 = [str(c) for c in clamps[2].sequent.context]
    assert any("x" in c and "1" in c for c in ctx3)
    # 5th obligation (post-loop assert): the exit frame (invariant + negated
    # guard over the fresh value) is in context
    last = clamps[5].sequent.context
    assert any("!" in str(c) for c in last), last


def test_havoc_renames_the_goal_side() -> None:
    src = """
procedure h(x: int)
{
  assume x >= 5;
  havoc x;
  assert x >= 5;
}
"""
    result = import_module(src, "h.bpl")
    obl = result.procedures["h"].obligations[0]
    from uvil.artifacts import to_smt

    ctx = [to_smt(c) for c in obl.sequent.context]
    goal = to_smt(obl.sequent.goal)
    # the pre-havoc antecedent stays (about the OLD x); the goal is over the
    # fresh havoc'd value, so the old assumption cannot discharge it
    assert "(>= x 5)" in ctx
    assert goal.startswith("(>= x!")
    assert "!0" in goal


def test_assumes_join_the_context() -> None:
    src = """
procedure a(x: int)
{
  assume x >= 5;
  assert x >= 3;
}
"""
    result = import_module(src, "a.bpl")
    obl = result.procedures["a"].obligations[0]
    from uvil.artifacts import to_smt

    rendered = [to_smt(c) for c in obl.sequent.context]
    assert "(>= x 5)" in rendered, rendered


def test_var_sorts_populated() -> None:
    result = import_module(FULL_MODULE, "full.bpl")
    arrays = result.procedures["arrays"].obligations[0]
    assert arrays.sequent.var_sorts == {"a": "(Array Int Int)"}
    seqs = result.procedures["seqs"].obligations[0]
    assert seqs.sequent.var_sorts == {"s": "(Seq Int)"}


def test_out_of_subset_if_is_loud() -> None:
    src = """procedure bad(x: int)
{
  if x > 0 { y := 1; }
}
"""
    result = import_module(src, "bad.bpl")
    assert not result.ok
    assert result.procedures.get("bad") is None
    diag = result.diagnostics[0]
    assert diag.kind == "parse"
    assert diag.loc.line == 3
    assert "if x > 0 { y := 1; }" in diag.native_message


def test_unknown_identifier_is_loud() -> None:
    src = "procedure p()\n{\n  assert zzz >= 0;\n}\n"
    result = import_module(src, "p.bpl")
    assert not result.ok
    assert "zzz" in result.diagnostics[0].native_message


def test_uninterpreted_function_call_is_loud() -> None:
    src = """
function f(x: int) returns (int);
procedure p(x: int)
{
  assert f(x) >= 0;
}
"""
    result = import_module(src, "p.bpl")
    assert not result.ok
    assert "f" in result.diagnostics[0].native_message


def test_strict_parse_raises_with_verbatim_line() -> None:
    with pytest.raises(BoogieParseError) as e:
        parse_module("procedure p()\n{\n  call foo();\n}\n")
    assert "call foo();" in e.value.line_text


def test_term_vars_skips_bound_names() -> None:
    from uvil.artifacts.terms import Term

    body = Term(op="ge", args=[Term(op="var", args=["i"]), Term(op="const", args=[0])])
    q = Term(op="forall", args=["i", "Int", body])
    assert term_vars(q) == set()


def test_obligations_json_snapshot(snapshot: SnapshotAssertion) -> None:
    result = import_module(FULL_MODULE, "full.bpl")
    payload = [
        json.loads(o.model_dump_json()) for p in result.procedures.values() for o in p.obligations
    ]
    assert payload == snapshot
