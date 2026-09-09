"""Isabelle/HOL encoder: I4 sequents -> HOL theorems (the HOL-facing boundary).

The OpenTheory lesson (mirror of `adapters.lean.encode`): stay within the
linear-arith fragment where HOL and the shared theory PROVABLY agree; the
boundary is the whitelist, not an aspiration. For that fragment the generated
`by arith`/`by auto` theorems are the Isabelle twin of the shared sequent;
anything outside it is an `UnsupportedTermError` -> I9 `lossy` translation +
I7 `semantic-mismatch` - the downgrade is measured on the same corpus
families as the Lean slice, never hidden.

Documented boundary (mirrors the Lean encoder's discovery-pinned subset):
- linear Int arithmetic with `arith`; `ite` on Int via HOL's
  `(if ... then ... else ...)` (tactic `auto` - provisional until the live
  discovery tests pin the tactic set against the pinned bundle);
- div/mod ONLY with positive constant divisors (constant-pin propagation of
  context equalities `var == K`, shared with the Lean encoder) - Isabelle's
  `div`/`mod` on `int` are floored and agree with SMT-LIB Euclidean
  div/mod exactly there;
- Bool atoms as `p::bool` propositions with `auto` (the bool connective
  surface the corpus actually exercises);
- quantifier spines, Real, arrays, seq, nonlinear `*`, and opaque terms have
  NO HOL rendering in the boundary -> fail loud.
"""

from __future__ import annotations

from ...artifacts import Obligation, artifact_id
from ...artifacts.terms import Term, term_vars, to_smt
from ..lean.encode import _pin_constants

TARGET_KIND = "isabelle-hol-theorem"

# var_sorts values that have a HOL rendering (SMT sort string -> HOL type).
_HOL_SORTS = {"Int": "int", "Bool": "bool"}

_INT = "int"
_BOOL = "bool"

ISABELLE_BATCH_SIZE = 20  # theorems per theory file (startup amortization; discovery-timed)


class UnsupportedTermError(ValueError):
    """A term outside the HOL-facing boundary (fail loud, R3).

    `native_message` carries the verbatim SMT sexpr of the offending fragment
    so the emitted I7 `semantic-mismatch` / I9 `lossy` round-trips.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.native_message = message


def _unsupported(reason: str, frag: Term) -> UnsupportedTermError:
    try:
        sexpr = to_smt(frag)
    except ValueError:
        sexpr = repr(frag)
    return UnsupportedTermError(f"term outside the Isabelle/HOL boundary: {reason}\n{sexpr}")


def _is_int_const(t: Term) -> bool:
    return (
        t.op == "const"
        and bool(t.args)
        and isinstance(t.args[0], int)
        and not isinstance(t.args[0], bool)
    )


def _int_const(value: int) -> str:
    return f"({value})" if value < 0 else str(value)


class _HolEncoder:
    def __init__(self, var_sorts: dict[str, str]) -> None:
        self._sorts = var_sorts

    def sort_of(self, name: str) -> str:
        sort = self._sorts.get(name, "int")
        if sort not in _HOL_SORTS:
            raise _unsupported(
                f"variable {name!r} has unsupported sort {sort!r}",
                Term(op="var", args=[name]),
            )
        return _HOL_SORTS[sort]

    def term(self, t: Term) -> tuple[str, str]:
        """Render an Int/Bool-typed term; returns (hol_text, sort)."""
        op = t.op
        args = t.args

        if op == "var":
            name = args[0] if args and isinstance(args[0], str) else "?"
            return name, self.sort_of(name)

        if op == "const":
            value = args[0] if args else None
            if isinstance(value, bool):
                return ("True" if value else "False"), _BOOL
            if isinstance(value, int):
                return _int_const(value), _INT
            if isinstance(value, float):
                raise _unsupported("Real constants have no HOL boundary encoding", t)
            raise _unsupported(f"unsupported constant {value!r}", t)

        if op == "ite":
            if len(args) != 3 or not all(isinstance(a, Term) for a in args):
                raise _unsupported("ite requires (cond, then, else) terms", t)
            cond, then_t, else_t = (a for a in args if isinstance(a, Term))
            then_s, then_sort = self.term(then_t)
            else_s, else_sort = self.term(else_t)
            if then_sort != else_sort:
                raise _unsupported("ite branches have mismatched sorts", t)
            cond_s = self.prop(cond)
            return f"(if {cond_s} then {then_s} else {else_s})", then_sort

        if op in ("add", "sub", "mul", "neg", "intdiv", "mod"):
            return self._arith(t)

        if op in ("forall", "exists"):
            raise _unsupported("quantifiers are propositions", t)

        raise _unsupported(f"operator {op!r} has no HOL operand encoding", t)

    def _arith(self, t: Term) -> tuple[str, str]:
        op = t.op
        args = t.args
        if op == "neg":
            if len(args) != 1 or not isinstance(args[0], Term):
                raise _unsupported("neg requires one operand", t)
            (inner, sort) = self.term(args[0])
            if sort != _INT:
                raise _unsupported("negation over Bool operands", t)
            return f"(- {inner})", _INT

        operands = [a for a in args if isinstance(a, Term)]
        if len(operands) != len(args) or len(operands) < 2:
            raise _unsupported(f"{op!r} requires term operands", t)

        texts: list[str] = []
        for a in operands:
            (s, sort) = self.term(a)
            if sort != _INT:
                raise _unsupported(f"{op!r} over {sort} operands", t)
            texts.append(s)

        if op == "add":
            return ("(" + " + ".join(texts) + ")"), _INT
        if op == "sub":
            return ("(" + " - ".join(texts) + ")"), _INT
        if op == "mul":
            if len(texts) != 2:
                raise _unsupported("mul is binary", t)
            if not any(_is_int_const(a) for a in operands):
                raise _unsupported("nonlinear multiplication (both operands symbolic)", t)
            return f"({texts[0]} * {texts[1]})", _INT
        if op in ("intdiv", "mod"):
            divisor = operands[1]
            if not (
                _is_int_const(divisor) and isinstance(divisor.args[0], int) and divisor.args[0] > 0
            ):
                raise _unsupported(
                    "div/mod requires a positive constant divisor "
                    "(Isabelle int div/mod are floored and agree with SMT-LIB "
                    "Euclidean div/mod only for positive divisors)",
                    t,
                )
            symbol = "div" if op == "intdiv" else "mod"
            return f"({texts[0]} {symbol} {texts[1]})", _INT
        raise _unsupported(f"operator {op!r}", t)  # pragma: no cover - guarded above

    def prop(self, t: Term) -> str:
        """Render a Prop-position term (the goal / a context hypothesis)."""
        op = t.op
        args = t.args

        if op == "var":
            name = args[0] if args and isinstance(args[0], str) else "?"
            sort = self.sort_of(name)
            if sort == _BOOL:
                return name  # a bool atom is its own proposition in HOL
            raise _unsupported(f"bare {sort} variable in proposition position", t)

        if op == "const":
            value = args[0] if args else None
            if isinstance(value, bool):
                return "True" if value else "False"
            raise _unsupported(f"constant {value!r} in proposition position", t)

        if op in ("and", "or", "not", "implies"):
            parts = [self.prop(a) for a in args if isinstance(a, Term)]
            if len(parts) != len(args) or not parts:
                raise _unsupported(f"{op!r} requires term operands", t)
            if op == "not":
                return f"(¬ {parts[0]})"
            sep = {"and": " ∧ ", "or": " ∨ ", "implies": " ⟶ "}[op]
            return "(" + sep.join(parts) + ")"

        if op in ("eq", "neq", "lt", "le", "gt", "ge"):
            return self._relational(t)

        if op == "ite":
            raise _unsupported("ite over propositions (bool branches)", t)

        if op in ("forall", "exists"):
            if len(args) != 3 or not (isinstance(args[0], str) and isinstance(args[1], str)):
                raise _unsupported("quantifier requires (name, sort, body)", t)
            name, sort, body = args[0], args[1], args[2]
            if sort not in _HOL_SORTS:
                raise _unsupported(f"quantifier over sort {sort!r}", t)
            if not isinstance(body, Term):
                raise _unsupported("quantifier body must be a term", t)
            # Boundary: quantified hypotheses discharge only with simple
            # comparison bodies (mirrors the Lean discovery pin; HOL's arith
            # is not a general quantifier decision procedure either).
            if body.op not in ("eq", "neq", "lt", "le", "gt", "ge"):
                raise _unsupported(
                    "quantifier body must be a single Int comparison",
                    t,
                )
            inner = _HolEncoder({**self._sorts, name: sort})
            binder = {"int": f"{name}::int", "bool": f"{name}::bool"}[sort]
            return f"(⋀{binder}. {inner.prop(body)})"

        raise _unsupported(f"operator {op!r} has no HOL proposition encoding", t)

    def _relational(self, t: Term) -> str:
        op = t.op
        operands = [a for a in t.args if isinstance(a, Term)]
        if len(operands) != 2:
            raise _unsupported(f"{op!r} is binary", t)
        (a_text, a_sort) = self.term(operands[0])
        (b_text, b_sort) = self.term(operands[1])
        if a_sort != b_sort:
            raise _unsupported(f"relational {op!r} over mixed sorts", t)
        symbol = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥", "eq": "=", "neq": "≠"}[op]
        return f"({a_text} {symbol} {b_text})"


def theorem_name(obl: Obligation) -> str:
    """Stable theorem name: `uvil_obl_` + 12-hex obligation-id hash prefix."""
    return "uvil_obl_" + artifact_id(obl).rsplit(":", 1)[-1][:12]


def _mentions_bool(obl_names: dict[str, str]) -> bool:
    return any(sort == "bool" for sort in obl_names.values())


def _mentions_ite(term: Term) -> bool:
    if term.op == "ite":
        return True
    return any(isinstance(a, Term) and _mentions_ite(a) for a in term.args)


def hol_statement(obl: Obligation) -> tuple[str, str]:
    """The HOL statement of an obligation + its tactic: `(statement, tactic)`.

    The binder list is the sorted free-variable set with `var_sorts` driving
    int/bool; absent sort info defaults to int (the sequent convention).
    Tactics: `arith` on pure linear-int statements, `auto` when bool atoms
    or `ite` are present (provisional pending the live discovery tests,
    ADR 0005).
    """
    context, goal = _pin_constants(obl)
    encoder = _HolEncoder(dict(obl.sequent.var_sorts))

    hypothesis_props = [encoder.prop(c) for c in context]
    goal_prop = encoder.prop(goal)

    names = sorted(term_vars(goal) | {v for c in context for v in term_vars(c)})
    binders: list[str] = []
    for name in names:
        sort = encoder.sort_of(name)
        binders.append(f"{name}::{sort}")

    body = goal_prop
    for hyp in reversed(hypothesis_props):
        body = f"{hyp} ⟹ {body}"
    quantified = "".join(f"⋀{b}. " for b in binders)
    statement = f"{quantified}{body}"

    sorts_of_names = {n: encoder.sort_of(n) for n in names}
    if (
        _mentions_bool(sorts_of_names)
        or _mentions_ite(goal)
        or any(_mentions_ite(c) for c in context)
    ):
        tactic = "auto"
    else:
        tactic = "arith"
    return statement, tactic


def to_hol_theorem(obl: Obligation) -> str:
    """Encode an obligation as a standalone Isabelle/HOL theorem line.

    Raises `UnsupportedTermError` for anything outside the boundary (the
    caller emits I9 `lossy` + I7 `semantic-mismatch`; the obligation stays
    open). Declared variables with unsupported sorts fail loud even if the
    term happens not to reference them (the slice metrics stay honest).
    """
    for name, sort in sorted(obl.sequent.var_sorts.items()):
        if sort not in _HOL_SORTS:
            raise _unsupported(
                f"variable {name!r} has unsupported sort {sort!r}",
                Term(op="var", args=[name]),
            )
    statement, tactic = hol_statement(obl)
    return f'theorem {theorem_name(obl)}: "{statement}" by {tactic}'


def theory_file(theorems: list[str], name: str) -> str:
    """Wrap theorems into one batched theory file (startup amortization)."""
    body = "\n\n".join(theorems)
    return f"theory {name}\n  imports Main\nbegin\n\n{body}\n\nend\n"
