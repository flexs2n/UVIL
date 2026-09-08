"""Core assertion language: terms over the shared theories.

A small, hash-stable AST covering the SMT-LIB v2 core-theory subset named in the
design spec (§5.2, I2): Int, Real, Bool, arrays, bitvectors, ADTs, plus the
`Opaque(ty, axiom_id)` escape hatch for backend-only constructs. The AST carries
structure, not meaning (P6): adapters interpret it into backend syntax.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict

TermArg = Union["Term", int, float, bool, str, None]

CORE_SORTS = ("int", "real", "bool", "array", "bitvec", "adt", "opaque")

_SMT_OPS: dict[str, str] = {
    "and": "and",
    "or": "or",
    "not": "not",
    "implies": "=>",
    "eq": "=",
    "neq": "distinct",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
    "add": "+",
    "sub": "-",
    "mul": "*",
    "neg": "-",
    "intdiv": "div",
    "realdiv": "/",
    "mod": "mod",
    "ite": "ite",
    "select": "select",
    "store": "store",
    "seq.len": "seq.len",
    "seq.nth": "seq.nth",
    "seq.empty": "seq.empty",
    "seq.cons": "seq.cons",
    "seq.update": "seq.update",
}


class Term(BaseModel):
    """A term in the core assertion language.

    - `op="var"`: args = [name]
    - `op="const"`: args = [scalar] (int/float/bool)
    - `op="opaque"`: args = [ty, axiom_id] - the `Opaque(ty, axiom_id)` escape hatch
    - quantifiers: `op="forall"|"exists"`, args = [var_name, sort, body]
    - anything else: op is a core operator, args are operands
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: str
    args: list[TermArg] = []


def var(name: str) -> Term:
    return Term(op="var", args=[name])


def const(value: int | float | bool) -> Term:
    return Term(op="const", args=[value])


def opaque(ty: str, axiom_id: str) -> Term:
    return Term(op="opaque", args=[ty, axiom_id])


def _wrap(op: str, *args: TermArg) -> Term:
    return Term(op=op, args=list(args))


def t_and(*args: TermArg) -> Term:
    return _wrap("and", *args)


def t_or(*args: TermArg) -> Term:
    return _wrap("or", *args)


def t_not(arg: TermArg) -> Term:
    return _wrap("not", arg)


def t_implies(a: TermArg, b: TermArg) -> Term:
    return _wrap("implies", a, b)


def t_eq(a: TermArg, b: TermArg) -> Term:
    return _wrap("eq", a, b)


def t_neq(a: TermArg, b: TermArg) -> Term:
    return _wrap("neq", a, b)


def t_lt(a: TermArg, b: TermArg) -> Term:
    return _wrap("lt", a, b)


def t_le(a: TermArg, b: TermArg) -> Term:
    return _wrap("le", a, b)


def t_gt(a: TermArg, b: TermArg) -> Term:
    return _wrap("gt", a, b)


def t_ge(a: TermArg, b: TermArg) -> Term:
    return _wrap("ge", a, b)


def t_add(*args: TermArg) -> Term:
    return _wrap("add", *args)


def t_sub(a: TermArg, b: TermArg) -> Term:
    return _wrap("sub", a, b)


def t_mul(a: TermArg, b: TermArg) -> Term:
    return _wrap("mul", a, b)


def t_ite(c: TermArg, t: TermArg, e: TermArg) -> Term:
    return _wrap("ite", c, t, e)


def t_select(a: TermArg, i: TermArg) -> Term:
    return _wrap("select", a, i)


def t_store(a: TermArg, i: TermArg, v: TermArg) -> Term:
    return _wrap("store", a, i, v)


def t_forall(name: str, sort: str, body: TermArg) -> Term:
    return _wrap("forall", name, sort, body)


def t_exists(name: str, sort: str, body: TermArg) -> Term:
    return _wrap("exists", name, sort, body)


def _render_const(value: int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value):
            return f"{value:.1f}"
        return repr(value)
    return str(value)


def to_smt(term: Term) -> str:
    """Render a Term as an SMT-LIB v2 expression (shared-theory subset)."""
    op = term.op
    args = term.args

    if op == "var":
        if not args or not isinstance(args[0], str):
            raise ValueError("var term requires a name argument")
        return args[0]
    if op == "const":
        if not args or not isinstance(args[0], (int, float, bool)):
            raise ValueError("const term requires a scalar argument")
        return _render_const(args[0])
    if op == "opaque":
        if len(args) != 2 or not all(isinstance(a, str) for a in args):
            raise ValueError("opaque term requires (ty, axiom_id) string arguments")
        raise ValueError(
            f"opaque term (ty={args[0]!r}, axiom={args[1]!r}) has no shared-theory "
            "rendering; resolve it against its axiom before SMT emission"
        )
    if op in ("forall", "exists"):
        if len(args) != 3 or not (isinstance(args[0], str) and isinstance(args[1], str)):
            raise ValueError(f"{op} term requires (name, sort, body) arguments")
        body = args[2]
        body_s = to_smt(body) if isinstance(body, Term) else str(body)
        return f"({op} (({args[0]} {args[1]})) {body_s})"

    smt_op = _SMT_OPS.get(op)
    if smt_op is None:
        raise ValueError(f"unknown core operator: {op!r}")
    rendered = []
    for a in args:
        if isinstance(a, Term):
            rendered.append(to_smt(a))
        elif isinstance(a, bool):
            rendered.append("true" if a else "false")
        elif isinstance(a, (int, float)):
            rendered.append(_render_const(a))
        elif isinstance(a, str):
            rendered.append(a)
        else:
            raise ValueError(f"unsupported argument for {op!r}: {a!r}")
    return f"({smt_op} {' '.join(rendered)})"


def term_vars(term: Term) -> set[str]:
    """Free variables of a term (quantifier-bound names excluded)."""
    out: set[str] = set()
    if term.op == "var" and term.args and isinstance(term.args[0], str):
        out.add(term.args[0])
        return out
    if term.op in ("forall", "exists"):
        bound = term.args[0] if term.args and isinstance(term.args[0], str) else None
        body = term.args[2] if len(term.args) > 2 else None
        inner = term_vars(body) if isinstance(body, Term) else set()
        return {v for v in inner if v != bound}
    for a in term.args:
        if isinstance(a, Term):
            out |= term_vars(a)
    return out
