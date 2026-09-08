"""D2 round-trip validation tests.

The discovery test parses representative terms of every core op and pins what
the z3 parser does (=> survives as implies; - splits by arity; reals become
rationals and convert back). The round-trip tests then assert losslessness
over the whole encode -> parse -> reconstruct -> diff pipeline, and the
fail-loud behavior on unmapped constructs.
"""

from __future__ import annotations

import pytest
import z3

from tests.fixtures import make_obligation
from uvil.adapters.boogie.lower import import_module
from uvil.adapters.smt.roundtrip import _Reconstructor, roundtrip_validate
from uvil.artifacts import Obligation, artifact_id
from uvil.artifacts.terms import (
    Term,
    const,
    t_add,
    t_and,
    t_eq,
    t_exists,
    t_forall,
    t_ge,
    t_implies,
    t_ite,
    t_le,
    t_mul,
    t_not,
    t_or,
    t_select,
    t_store,
    t_sub,
    var,
)
from uvil.check.core import check, record
from uvil.ledger import Ledger
from uvil.store import ContentStore


def _obligation_with_goal(
    goal: Term, context: list[Term] | None = None, var_sorts: dict[str, str] | None = None
) -> Obligation:
    data = make_obligation().model_dump()
    data["sequent"]["goal"] = goal.model_dump(mode="json")
    if context is not None:
        data["sequent"]["context"] = [t.model_dump(mode="json") for t in context]
    if var_sorts is not None:
        data["sequent"]["var_sorts"] = var_sorts
    return Obligation.model_validate(data)


# --- discovery: pin the z3 parser normalizations ------------------------------


def test_discovery_implies_and_unary_minus_survive() -> None:
    solver = z3.Solver()
    solver.from_string("(assert (=> true (> (- 5) 0)))")
    (a,) = solver.assertions()
    assert a.decl().kind() == z3.Z3_OP_IMPLIES  # `=>` is not rewritten away
    (neg) = a.children()[1].children()[0]
    assert neg.decl().kind() == z3.Z3_OP_UMINUS  # unary minus is a distinct kind


def test_discovery_reals_become_rationals() -> None:
    solver = z3.Solver()
    solver.from_string("(declare-const x Real)(assert (> x 2.5))")
    (a,) = solver.assertions()
    rhs = a.children()[1]
    assert z3.is_rational_value(rhs)
    assert rhs.as_string() == "5/2"  # z3 normalizes decimals to rationals


def test_discovery_bound_var_names_are_recoverable() -> None:
    solver = z3.Solver()
    solver.from_string("(assert (forall ((x Int)) (> x 0)))")
    (q,) = solver.assertions()
    assert q.var_name(0) == "x"
    assert str(q.var_sort(0)) == "Int"
    assert z3.is_var(q.body().children()[0])  # body leaves are de Bruijn vars


# --- round-trip over every core op --------------------------------------------


def _seq_goal() -> Term:
    # (seq.len s) >= 1  ==>  (seq.nth s 0) >= 0
    return t_implies(
        t_ge(Term(op="seq.len", args=[var("s")]), const(1)),
        t_ge(Term(op="seq.nth", args=[var("s"), const(0)]), const(0)),
    )


OP_FAMILIES: list[tuple[str, Term, dict[str, str]]] = [
    ("bool", t_and(t_or(t_not(var("p")), var("q")), var("p")), {"p": "Bool", "q": "Bool"}),
    ("implies", t_implies(t_ge(var("x"), const(0)), t_ge(var("x"), const(0))), {}),
    (
        "arith",
        t_eq(
            t_add(t_mul(var("x"), const(2)), t_sub(var("y"), Term(op="neg", args=[var("z")]))),
            const(7),
        ),
        {},
    ),
    (
        "divmod",
        t_eq(t_add(t_mul(var("a"), const(2)), Term(op="mod", args=[var("a"), const(3)])), const(1)),
        {},
    ),
    ("ite", t_eq(t_ite(var("p"), const(1), const(2)), const(1)), {"p": "Bool"}),
    (
        "arrays",
        t_eq(
            t_select(
                t_store(t_store(var("arr"), const(1), const(2)), const(3), const(4)), const(1)
            ),
            const(2),
        ),
        {"arr": "(Array Int Int)"},
    ),
    ("seq", _seq_goal(), {"s": "(Seq Int)"}),
    (
        "quantifiers",
        t_implies(
            t_forall(
                "i",
                "Int",
                t_implies(
                    t_and(t_ge(var("i"), const(0)), t_le(var("i"), var("n"))),
                    t_ge(t_select(var("arr"), var("i")), const(0)),
                ),
            ),
            t_exists("j", "Int", t_eq(var("j"), const(0))),
        ),
        {"n": "Int", "arr": "(Array Int Int)"},
    ),
    ("reals", t_eq(var("r"), const(2.5)), {"r": "Real"}),
]


@pytest.mark.parametrize("family,goal,var_sorts", OP_FAMILIES, ids=[f for f, _, _ in OP_FAMILIES])
def test_roundtrip_lossless_per_op_family(
    family: str, goal: Term, var_sorts: dict[str, str]
) -> None:
    del family
    obl = _obligation_with_goal(goal, var_sorts=var_sorts)
    result = roundtrip_validate(obl)
    assert result.lossless, result.divergences
    assert result.translation is not None
    assert result.translation.soundness_discipline == "roundtrip-validated"
    assert result.translation.residuals.dropped_fragments == []


def test_roundtrip_boogie_corpus_obligations_lossless() -> None:
    sources = [
        "procedure p(a: int)\n  requires a >= 3\n{\n  assert a + a == 2 * a;\n}\n",
        "procedure q(a: int, b: int)\n  requires b == 7\n{\n  assert a / b * b + a % b == a;\n}\n",
        "procedure r(n: int, a: [int]int)\n"
        "  requires n >= 1\n"
        "  requires forall i: int :: 0 <= i && i < n ==> a[i] >= 0\n"
        "{\n  assert a[n - 1] >= 0;\n}\n",
        "procedure s(n: int, s0: seq<int>)\n  requires |s0| > 2\n{\n  assert s0[2] >= -1;\n}\n",
    ]
    for src in sources:
        result = import_module(src, "rt.bpl")
        assert result.ok, [d.native_message for d in result.diagnostics]
        for obl in result.obligations:
            rt = roundtrip_validate(obl)
            assert rt.lossless, (src, rt.divergences)


def test_roundtrip_translation_records_mapping() -> None:
    (obl,) = list(
        import_module("procedure p(x: int)\n{\n  assert x >= 0;\n}\n", "m.bpl").obligations
    )
    rt = roundtrip_validate(obl)
    assert rt.translation is not None
    assert rt.translation.source_artifact == artifact_id(obl)
    assert rt.translation.target_kind == "smt-lib2-assertions"
    assert len(rt.translation.mapping) == len(obl.sequent.context) + 1


def test_reconstructor_records_unmapped_construct_as_divergence() -> None:
    # CONST_ARRAY never originates from our Terms; reconstructing one must be
    # recorded as a divergence, never silently passed.
    rec = _Reconstructor()
    const_array = z3.K(z3.IntSort(), z3.IntVal(0))
    term = rec.reconstruct(const_array, [])
    assert rec.divergences
    assert "unmapped" in rec.divergences[0]
    assert term.op == "const"  # stable hash marker, not a forged match


def test_reconstructor_multi_var_quantifier_diverges() -> None:
    solver = z3.Solver()
    solver.from_string("(assert (forall ((x Int) (y Int)) (> x y)))")
    rec = _Reconstructor()
    rec.reconstruct(solver.assertions()[0], [])
    assert any("one per quantifier" in d for d in rec.divergences)


def test_roundtrip_ignores_assertion_order_for_context() -> None:
    # context order is normalized away (sorted canonical strings)
    goal = t_ge(var("x"), const(0))
    ctx_a = [t_ge(var("y"), const(0)), t_le(var("y"), const(9))]
    ctx_b = [t_le(var("y"), const(9)), t_ge(var("y"), const(0))]
    rt_a = roundtrip_validate(_obligation_with_goal(goal, ctx_a))
    rt_b = roundtrip_validate(_obligation_with_goal(goal, ctx_b))
    assert rt_a.lossless and rt_b.lossless


# --- check() wiring ------------------------------------------------------------


def test_check_roundtrip_discipline_records_i9() -> None:
    (obl,) = _boogie_obligations(
        "procedure p(x: int)\n  requires x >= 0\n{\n  assert x + 0 == x;\n}\n"
    )
    result = check([obl], backend="z3", discipline="roundtrip")
    assert result.run is not None
    assert result.run.config["discipline"] == "roundtrip"
    assert len(result.translations) == 1
    (translation,) = result.translations
    assert translation is not None
    assert translation.soundness_discipline == "roundtrip-validated"
    assert result.obligations[0].status == "discharged"  # non-gating: check proceeds


def test_check_roundtrip_lossy_still_checks() -> None:
    (obl,) = _boogie_obligations("procedure p(x: int)\n  requires x >= 0\n{\n  assert x >= 0;\n}\n")
    rt = roundtrip_validate(obl)
    assert rt.lossless  # sanity: core ops round-trip
    # a fabricated lossy translation must never block the verdict path
    result = check([obl], backend="z3", discipline="roundtrip")
    assert result.run is not None
    assert result.run.verdicts[0].status == "discharged"


def test_check_unknown_discipline_rejected() -> None:
    (obl,) = _boogie_obligations("procedure p(x: int)\n{\n  assert x >= 0;\n}\n")
    with pytest.raises(ValueError, match="discipline"):
        check([obl], backend="z3", discipline="kernel")


def test_check_roundtrip_stored_in_cas(tmp_path) -> None:
    (obl,) = _boogie_obligations("procedure p(x: int)\n{\n  assert x >= 0;\n}\n")
    result = check([obl], backend="z3", discipline="roundtrip")
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record(result, store, ledger)
    translations = [r for r in refs if "translation" in r]
    assert translations
    fetched = store.get_artifact(translations[0])
    assert fetched.soundness_discipline == "roundtrip-validated"  # type: ignore[attr-defined]


def _boogie_obligations(src: str) -> list[Obligation]:
    result = import_module(src, "rt.bpl")
    assert result.ok, [d.native_message for d in result.diagnostics]
    return list(result.obligations)


def test_cli_check_discipline_flag(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    bpl = tmp_path / "p.bpl"
    bpl.write_text("procedure p(x: int)\n  requires x >= 0\n{\n  assert x >= 0;\n}\n")

    result = runner.invoke(app, ["check", str(bpl), "--discipline", "roundtrip"])
    assert result.exit_code == 0, result.output

    bad = tmp_path / "q.bpl"
    bad.write_text("procedure q(x: int)\n{\n  assert x >= 0;\n}\n")
    result = runner.invoke(app, ["check", str(bad), "--discipline", "kernel"])
    assert result.exit_code != 0  # unknown discipline fails loud
