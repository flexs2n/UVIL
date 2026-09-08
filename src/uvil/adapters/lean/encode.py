"""Lean theorem encoder: I4 sequents -> standalone `by omega` theorem files.

Discovery findings pinned for the M3 toolchain (leanprover/lean4:v4.33.1,
see tests/test_lean_discovery.py):

- `omega` proves linear Int arithmetic (conjunctive/disjunctive Int
  comparisons in hypotheses and goals).
- Bool atoms work only as direct literal-coerced facts (`p = true`,
  `p = false`); boolean connectives over pure Bool atoms are NOT
  omega-provable, and neither is general Bool-Bool equality (`p = q`).
- `ite` on Int operands is handled (minmax/abs-bound corpus families join the
  slice).
- Lean 4.33 `Int` `/`/`%` are floored (`(-7)/2 = -4`, `(-7)%2 = 1`), which
  MATCHES SMT-LIB Euclidean `div`/`mod` for positive divisors. The encoder
  still restricts `/`/`%` to provably-positive constant divisors (via
  constant-pin propagation of context equalities `var == K`) - Euclidean
  semantics is only well-behaved there; anything else is
  `UnsupportedTermError` (fail loud, R3).
- Quantifiers over Int are supported ONLY with simple comparison bodies:
  `∀ i, i < n` and `∃ j, j = 3` discharge, but implication/conjunction spines
  inside a quantified hypothesis do NOT (pinned by discovery) - the encoder
  fails loud on those shapes.
- Real, arrays, seq, nonlinear `*`, and opaque terms have no encoding:
  `UnsupportedTermError` carries the verbatim SMT sexpr for the I7
  `semantic-mismatch` diagnostic.

The generated theorem is self-contained: `lean file.lean` under the pinned
toolchain is the entire checking procedure (offline kernel attestation).
"""

from __future__ import annotations

from ...artifacts import Obligation, artifact_id
from ...artifacts.terms import Term, term_vars, to_smt
from ..boogie.lower import substitute

TARGET_KIND = "lean4-theorem"

# var_sorts values that have a Lean rendering (SMT sort string -> Lean type).
_LEAN_SORTS = {"Int": "Int", "Bool": "Bool"}

_INT = "Int"
_BOOL = "Bool"


class UnsupportedTermError(ValueError):
    """A term outside the omega-provable LIA subset (fail loud, R3).

    `native_message` carries the verbatim SMT sexpr of the offending fragment
    so the emitted I7 `semantic-mismatch` round-trips.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.native_message = message


def _unsupported(reason: str, frag: Term) -> UnsupportedTermError:
    try:
        sexpr = to_smt(frag)
    except ValueError:
        sexpr = repr(frag)
    return UnsupportedTermError(f"term outside the Lean/omega subset: {reason}\n{sexpr}")


def _is_int_const(t: Term) -> bool:
    return (
        t.op == "const"
        and bool(t.args)
        and isinstance(t.args[0], int)
        and not isinstance(t.args[0], bool)
    )


def _int_const(value: int) -> str:
    return f"({value})" if value < 0 else str(value)


class _Encoder:
    def __init__(self, var_sorts: dict[str, str]) -> None:
        self._sorts = var_sorts

    def sort_of(self, name: str) -> str:
        sort = self._sorts.get(name, "Int")
        if sort not in _LEAN_SORTS:
            raise _unsupported(
                f"variable {name!r} has unsupported sort {sort!r}",
                Term(op="var", args=[name]),
            )
        return _LEAN_SORTS[sort]

    # -- term positions (Int- or Bool-typed) -----------------------------------

    def term(self, t: Term) -> tuple[str, str]:
        """Render an Int/Bool-typed term; returns (lean_text, sort)."""
        op = t.op
        args = t.args

        if op == "var":
            name = args[0] if args and isinstance(args[0], str) else "?"
            return name, self.sort_of(name)

        if op == "const":
            value = args[0] if args else None
            if isinstance(value, bool):
                return ("true" if value else "false"), _BOOL
            if isinstance(value, int):
                return _int_const(value), _INT
            if isinstance(value, float):
                raise _unsupported("Real constants have no omega encoding", t)
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

        raise _unsupported(f"operator {op!r} has no Lean operand encoding", t)

    def _arith(self, t: Term) -> tuple[str, str]:
        op = t.op
        args = t.args
        if op == "neg":
            if len(args) != 1 or not isinstance(args[0], Term):
                raise _unsupported("neg requires one operand", t)
            (inner, sort) = self.term(args[0])
            if sort != _INT:
                raise _unsupported("negation over Bool operands", t)
            return f"(-{inner})", _INT

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
            # LIA guard: multiplication only when one side is a literal.
            if not any(_is_int_const(a) for a in operands):
                raise _unsupported("nonlinear multiplication (both operands symbolic)", t)
            return f"({texts[0]} * {texts[1]})", _INT
        if op in ("intdiv", "mod"):
            # Divisor must be a positive integer literal: Lean's floored Int
            # division matches SMT-LIB Euclidean div/mod only for positive
            # divisors (discovery-pinned); other shapes stay unsupported.
            divisor = operands[1]
            if not (
                _is_int_const(divisor) and isinstance(divisor.args[0], int) and divisor.args[0] > 0
            ):
                raise _unsupported(
                    "div/mod requires a positive constant divisor "
                    "(Lean / and % are floored and agree with SMT-LIB "
                    "Euclidean div/mod only for positive divisors)",
                    t,
                )
            symbol = "/" if op == "intdiv" else "%"
            return f"({texts[0]} {symbol} {texts[1]})", _INT
        raise _unsupported(f"operator {op!r}", t)  # pragma: no cover - guarded above

    # -- proposition positions --------------------------------------------------

    def prop(self, t: Term) -> str:
        """Render a Prop-position term (the goal / a context hypothesis)."""
        op = t.op
        args = t.args

        if op == "var":
            name = args[0] if args and isinstance(args[0], str) else "?"
            sort = self.sort_of(name)
            if sort == _BOOL:
                # Bare Bool variables coerce via `= true` (omega's idiom).
                return f"{name} = true"
            raise _unsupported(f"bare {sort} variable in proposition position", t)

        if op == "const":
            value = args[0] if args else None
            if isinstance(value, bool):
                return f"{'true' if value else 'false'} = true"
            raise _unsupported(f"constant {value!r} in proposition position", t)

        if op in ("and", "or", "not", "implies"):
            parts = [self.prop(a) for a in args if isinstance(a, Term)]
            if len(parts) != len(args) or not parts:
                raise _unsupported(f"{op!r} requires term operands", t)
            if op == "not":
                return f"(¬{parts[0]})"
            sep = {"and": " ∧ ", "or": " ∨ ", "implies": " → "}[op]
            return "(" + sep.join(parts) + ")"

        if op in ("eq", "neq", "lt", "le", "gt", "ge"):
            return self._relational(t)

        if op == "ite":
            # Prop-typed ite (branches are propositions) is outside the slice.
            raise _unsupported("ite over propositions (Bool branches)", t)

        if op in ("forall", "exists"):
            if len(args) != 3 or not (isinstance(args[0], str) and isinstance(args[1], str)):
                raise _unsupported("quantifier requires (name, sort, body)", t)
            name, sort, body = args[0], args[1], args[2]
            if sort not in _LEAN_SORTS:
                raise _unsupported(f"quantifier over sort {sort!r}", t)
            if not isinstance(body, Term):
                raise _unsupported("quantifier body must be a term", t)
            # Discovery pin: omega discharges quantified hypotheses only with
            # simple comparison bodies; implication/conjunction spines inside
            # a quantifier do NOT work - fail loud instead of emitting a
            # theorem the kernel will reject.
            if body.op not in ("eq", "neq", "lt", "le", "gt", "ge"):
                raise _unsupported(
                    "quantifier body must be a single Int comparison "
                    "(omega does not discharge implication/conjunction spines "
                    "inside quantified hypotheses)",
                    t,
                )
            inner = _Encoder({**self._sorts, name: sort})
            return f"({'∀' if op == 'forall' else '∃'} {name} : {sort}, {inner.prop(body)})"

        raise _unsupported(f"operator {op!r} has no Lean proposition encoding", t)

    def _relational(self, t: Term) -> str:
        op = t.op
        operands = [a for a in t.args if isinstance(a, Term)]
        if len(operands) != 2:
            raise _unsupported(f"{op!r} is binary", t)
        (a_text, a_sort) = self.term(operands[0])
        (b_text, b_sort) = self.term(operands[1])
        if a_sort != b_sort:
            raise _unsupported(f"relational {op!r} over mixed sorts", t)
        if a_sort == _BOOL:
            # omega only sees Bool atoms through `= true`: general Bool-Bool
            # equality is NOT omega-provable (discovery finding) - fail loud
            # except the literal-coerced forms.
            if op in ("eq", "neq") and all(
                isinstance(o, Term) and o.op == "const" and isinstance(o.args[0], bool)
                for o in operands
            ):
                body = f"({a_text} = {b_text})"
                return body if op == "eq" else f"(¬{body})"
            raise _unsupported(
                "Bool relations beyond literal equality (e.g. `p = q`) are not omega-provable",
                t,
            )
        symbol = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥", "eq": "=", "neq": "≠"}[op]
        return f"({a_text} {symbol} {b_text})"


def _pin_constants(obl: Obligation) -> tuple[list[Term], Term]:
    """Constant-pin propagation: context equalities `var == K` (K an Int
    literal) are substituted through the whole sequent (reuses
    `lower.substitute`, which honors quantifier shadowing). This makes the
    divmod corpus family (`requires b == K`) encode to `/ K` - the documented,
    deterministic path to omega-provable div/mod."""
    pins: dict[str, Term] = {}
    for ctx in obl.sequent.context:
        if ctx.op == "eq" and len(ctx.args) == 2:
            for a, b in ((ctx.args[0], ctx.args[1]), (ctx.args[1], ctx.args[0])):
                if not (isinstance(a, Term) and isinstance(b, Term)):
                    continue
                if a.op == "var" and a.args and isinstance(a.args[0], str) and _is_int_const(b):
                    pins.setdefault(a.args[0], b)
                    break
    context = [substitute(c, pins) for c in obl.sequent.context]
    goal = substitute(obl.sequent.goal, pins)
    return context, goal


def theorem_name(obl: Obligation) -> str:
    """Stable theorem name: `uvil_obl_` + 12-hex obligation-id hash prefix."""
    return "uvil_obl_" + artifact_id(obl).rsplit(":", 1)[-1][:12]


def lean_statement(obl: Obligation) -> str:
    """The Lean statement text of an obligation (binders + sequent, no name
    and no proof) - the recorded claim the BEq probe checks for faithfulness."""
    context, goal = _pin_constants(obl)
    encoder = _Encoder(dict(obl.sequent.var_sorts))

    hypothesis_props = [encoder.prop(c) for c in context]
    goal_prop = encoder.prop(goal)

    names = sorted(term_vars(goal) | {v for c in context for v in term_vars(c)})
    binders = " ".join(f"({name} : {encoder.sort_of(name)})" for name in names)
    if binders:
        binders = f"∀ {binders}, "

    sequent = "".join(f"{h} → " for h in hypothesis_props) + goal_prop
    return f"{binders}{sequent}"


def to_lean_theorem(obl: Obligation) -> str:
    """Encode an obligation as a standalone Lean 4 theorem discharged by omega.

    Raises `UnsupportedTermError` for anything outside the subset (the caller
    emits I7 `semantic-mismatch`; the obligation stays open). The binder list
    is the sorted free-variable set with `var_sorts` driving Int/Bool; absent
    sort info defaults to Int (the sequent convention).
    """
    # Unsupported sorts on any *declared* variable fail loud even if the term
    # happens not to reference them, so the slice metrics stay honest.
    for name, sort in sorted(obl.sequent.var_sorts.items()):
        if sort not in _LEAN_SORTS:
            raise _unsupported(
                f"variable {name!r} has unsupported sort {sort!r}",
                Term(op="var", args=[name]),
            )

    return f"theorem {theorem_name(obl)} : {lean_statement(obl)} := by omega"
