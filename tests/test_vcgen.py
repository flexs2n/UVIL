"""WI-1 discovery tests: the WP VCG's sequent shapes, pinned BEFORE implementation.

Each test hand-computes the weakest-precondition sequents for one probe shape
(scalar assign, array-store assign, havoc rename, while with invariant,
assert-folding, no-invariant loop) and pins them here first; the implementation
in `uvil.adapters.boogie.vcgen` is green exactly when these hold. The renaming
scheme pinned by these tests:

- Assignment/havoc handling is a forward walk with a variable map; goals are
  substituted with `lower.substitute` (quantifier-shadowing honoring).
- `havoc x` and loop-exit renaming introduce fresh names `<name>!<n>` (`!` is
  outside the Boogie identifier charset, so collisions are impossible); a
  fresh name is a free variable of the sequent, implicitly universally
  quantified by the SMT validity check - that is exactly havoc semantics.
- An `assert A` folds `A` into the path: downstream obligations assume it
  (Boogie's passive-form discipline).
- A `while G invariant I1..In` emits, in program order: one initiation
  obligation (`path ⊢ I1 ∧ .. ∧ In`), body-internal assert obligations, and
  one preservation obligation (`path, I@head, G ⊢ I@end`); the exit frame
  renames modified variables fresh and appends `I@exit` and `¬G` to the path.
  A loop with no invariants emits no init/preservation obligations and the
  exit frame assumes only `¬G`.
- `assert A by { B }` proves A under the by-block's assumptions (the outer
  obligation's context carries them); nested asserts keep their own
  obligations, emitted before the outer one.
"""

from __future__ import annotations

from uvil.adapters.boogie.lower import import_module
from uvil.adapters.smt.backends import verdict_status
from uvil.artifacts import to_smt
from uvil.check.core import SmtBackend


def _import(src: str):
    result = import_module(src, "vc.bpl")
    assert result.ok, [d.native_message for d in result.diagnostics]
    return result


def _rendered(obl):
    ctx = [to_smt(c) for c in obl.sequent.context]
    return ctx, to_smt(obl.sequent.goal)


def _status(obl) -> str:
    return verdict_status(SmtBackend("z3").run(obl, budget=2000))


# --- scalar assignment contributes to the goal (WP) ----------------------------


def test_scalar_assign_is_substituted_into_goal() -> None:
    result = _import(
        """
procedure p(x: int)
  requires x >= 0
{
  x := x + 1;
  assert x >= 1;
}
"""
    )
    (obl,) = result.obligations
    ctx, goal = _rendered(obl)
    assert ctx == ["(>= x 0)"]
    assert goal == "(>= (+ x 1) 1)"
    assert obl.origin_backend == "boogie-wp"
    assert _status(obl) == "discharged"  # M1 refuted this (assignment ignored)


def test_array_store_assign_uses_store_term() -> None:
    result = _import(
        """
procedure q(a: [int]int, i: int, v: int)
{
  a[i] := v;
  assert a[i] == v;
}
"""
    )
    (obl,) = result.obligations
    _, goal = _rendered(obl)
    assert goal == "(= (select (store a i v) i) v)"
    assert _status(obl) == "discharged"


# --- havoc renames the variable (fresh free var, not a dropped assumption) ------


def test_havoc_renames_goal_side_and_keeps_old_antecedent() -> None:
    result = _import(
        """
procedure h(x: int)
{
  assume x >= 5;
  havoc x;
  assert x >= 5;
}
"""
    )
    (obl,) = result.obligations
    ctx, goal = _rendered(obl)
    assert ctx == ["(>= x 5)"]  # antecedent about the pre-havoc x
    assert "!0" in goal and goal.startswith("(>= x!")  # goal over the fresh value
    assert _status(obl) == "refuted"  # unconstrained fresh value


def test_havoc_then_reassign_proves_via_new_value() -> None:
    result = _import(
        """
procedure h(x: int)
{
  havoc x;
  x := 3;
  assert x == 3;
}
"""
    )
    (obl,) = result.obligations
    assert _status(obl) == "discharged"


# --- while: initiation, preservation, exit frame --------------------------------


def test_loop_three_vc_shapes() -> None:
    result = _import(
        """
procedure l(n: int)
  requires n >= 1
{
  var i: int;
  assume i == 0;
  while i < n
    invariant i >= 0
  {
    i := i + 1;
  }
  assert i >= 0;
}
"""
    )
    proc = result.procedures["l"]
    assert len(proc.obligations) == 3
    init, preservation, post = proc.obligations

    init_ctx, init_goal = _rendered(init)
    assert init_ctx == ["(>= n 1)", "(= i 0)"]
    assert init_goal == "(>= i 0)"

    pres_ctx, pres_goal = _rendered(preservation)
    assert pres_ctx == ["(>= n 1)", "(= i 0)", "(>= i 0)", "(< i n)"]
    assert pres_goal == "(>= (+ i 1) 0)"

    post_ctx, post_goal = _rendered(post)
    # exit frame: i renamed fresh, invariant + negated guard assumed
    assert post_ctx == ["(>= n 1)", "(= i 0)", "(>= i!0 0)", "(not (< i!0 n))"]
    assert post_goal == "(>= i!0 0)"

    for obl in proc.obligations:
        assert _status(obl) == "discharged"


def test_loop_without_invariants_emits_no_init_or_preservation() -> None:
    result = _import(
        """
procedure w(x: int)
{
  var i: int;
  assume i == 0;
  while i < 10
  {
    i := i + 1;
  }
  assert true;
}
"""
    )
    proc = result.procedures["w"]
    assert len(proc.obligations) == 1  # the assert only; no init/preservation
    (post,) = proc.obligations
    ctx, _ = _rendered(post)
    assert "(not (< i!0 10))" in ctx


def test_asserts_are_assumed_downstream() -> None:
    result = _import(
        """
procedure s(x: int)
{
  assume x >= 0;
  assert x >= 0;
  assert x >= 1;
}
"""
    )
    proc = result.procedures["s"]
    assert len(proc.obligations) == 2
    first, second = proc.obligations
    ctx1, goal1 = _rendered(first)
    assert ctx1 == ["(>= x 0)"] and goal1 == "(>= x 0)"
    ctx2, goal2 = _rendered(second)
    assert ctx2 == ["(>= x 0)", "(>= x 0)"]  # the first assert joined the path
    assert goal2 == "(>= x 1)"
    assert _status(second) == "refuted"


def test_assert_by_proves_under_by_assumptions() -> None:
    result = _import(
        """
procedure b(x: int)
  requires x >= 5
{
  assert x >= 1 by {
    assume x >= 0;
  }
}
"""
    )
    (obl,) = result.obligations
    ctx, goal = _rendered(obl)
    assert ctx == ["(>= x 5)", "(>= x 0)"]
    assert goal == "(>= x 1)"
    assert _status(obl) == "discharged"


# --- the counterexample the M1 approximation wrongly discharged -----------------


def test_unproven_invariant_is_no_longer_an_assumption() -> None:
    """The W2 counterexample: an unproven (false) loop invariant let M1
    discharge the post-loop assert. The WP VCG must refute the initiation
    obligation instead (the invariant is now an obligation, not an
    assumption). Under M1 every obligation of this program was 'discharged'."""
    result = _import(
        """
procedure bad(n: int)
{
  var i: int;
  assume i == 0;
  while i < n
    invariant i == n
  {
    i := i + 1;
  }
  assert i == n;
}
"""
    )
    proc = result.procedures["bad"]
    assert len(proc.obligations) == 3
    init, _preservation, _post = proc.obligations
    init_ctx, init_goal = _rendered(init)
    assert init_ctx == ["(= i 0)"]
    assert init_goal == "(= i n)"
    assert _status(init) == "refuted"  # the red test: M1 had this discharged
    assert any(_status(o) == "refuted" for o in proc.obligations)


def test_two_asserts_share_one_procedure_distinct_identities() -> None:
    """Two obligations of one procedure must never collide on the cache
    identity (the sequent is part of the identity's canonical payload)."""
    from uvil.protocol import obligation_cache_identity

    result = _import(
        """
procedure s(x: int)
{
  assert x >= 0;
  assert x >= 1;
}
"""
    )
    ids = {obligation_cache_identity(o) for o in result.obligations}
    assert len(ids) == 2
