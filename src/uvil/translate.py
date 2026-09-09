"""Python mirror of lean/UVIL/Core.lean (the D1 verified translator).

The shared-theory Term AST (`uvil.artifacts.terms.Term`) is interpreted by
BOTH the Python side (here) and the Lean side (deep-embedded `Term.eval` /
`encodeLia` / `LiaExpr.interp`); the s-expression data format below travels
between them, and cross-language agreement is pinned by
tests/test_translator.py through the `uvil-translate-prove` runner.

The LIA subset mirrors the Lean `encodeLia` exactly:
- `mul`: at least one operand a literal (the literal factor is normalized to
  the front, `mulLit c e = c * e` - semantics unchanged);
- `intdiv`/`mod`: divisor a POSITIVE constant literal (SMT-LIB Euclidean
  div/mod agree with Python's floored `//`/`%` and Lean's floored `/`/`%`
  exactly there);
- everything else (Real, bool-position terms, quantifiers, opaque terms) is
  out of the translator's scope by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import Term
from .artifacts.terms import term_vars


@dataclass(frozen=True)
class Expr:
    """The deep-embedded LIA target (mirror of `Uvil.LiaExpr`)."""

    kind: str  # var | const | add | sub | mulLit | divConst | modConst
    c: int | None = None  # mulLit/divConst/modConst literal
    a: Expr | None = None
    b: Expr | None = None
    name: str | None = None


Env = dict[str, int]


def _is_int_const(t: Term) -> bool:
    return (
        t.op == "const"
        and bool(t.args)
        and isinstance(t.args[0], int)
        and not isinstance(t.args[0], bool)
    )


def encode_lia(term: Term) -> Expr | None:
    """Mirror of `Uvil.Term.encodeLia`: the guarded LIA translation; None
    outside the subset."""
    if term.op == "var":
        name = term.args[0]
        return Expr(kind="var", name=name) if isinstance(name, str) else None
    if term.op == "const":
        value = term.args[0]
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        return Expr(kind="const", c=value)
    if term.op == "neg":
        inner = encode_lia(term.args[0]) if isinstance(term.args[0], Term) else None
        return Expr(kind="sub", c=0, a=Expr(kind="const", c=0), b=inner) if inner else None
    if term.op in ("add", "sub"):
        ea = encode_lia(term.args[0]) if isinstance(term.args[0], Term) else None
        eb = encode_lia(term.args[1]) if isinstance(term.args[1], Term) else None
        if ea is None or eb is None:
            return None
        return Expr(kind=term.op, a=ea, b=eb)
    if term.op == "mul":
        ea = encode_lia(term.args[0]) if isinstance(term.args[0], Term) else None
        eb = encode_lia(term.args[1]) if isinstance(term.args[1], Term) else None
        if ea is None or eb is None:
            return None
        if ea.kind == "const":
            return Expr(kind="mulLit", c=ea.c, a=eb)
        if eb.kind == "const":
            return Expr(kind="mulLit", c=eb.c, a=ea)
        return None  # nonlinear: outside the LIA subset
    if term.op in ("intdiv", "mod"):
        ea = encode_lia(term.args[0]) if isinstance(term.args[0], Term) else None
        eb = encode_lia(term.args[1]) if isinstance(term.args[1], Term) else None
        if ea is None or eb is None or eb.kind != "const" or eb.c is None or eb.c <= 0:
            return None
        kind = "divConst" if term.op == "intdiv" else "modConst"
        return Expr(kind=kind, c=eb.c, a=ea)
    return None


def interp(expr: Expr, env: Env) -> int:
    """Mirror of `Uvil.LiaExpr.interp`."""
    match expr.kind:
        case "var":
            return env.get(expr.name or "", 0)
        case "const":
            return expr.c if expr.c is not None else 0
        case "add":
            return interp(expr.a, env) + interp(expr.b, env) if expr.a and expr.b else 0
        case "sub":
            return interp(expr.a, env) - interp(expr.b, env) if expr.a and expr.b else 0
        case "mulLit":
            return (expr.c or 0) * interp(expr.a, env) if expr.a else 0
        case "divConst":
            return interp(expr.a, env) // (expr.c or 1) if expr.a else 0
        case "modConst":
            return interp(expr.a, env) % (expr.c or 1) if expr.a else 0
        case _:  # pragma: no cover - the kind set is closed above
            raise ValueError(f"unknown expr kind {expr.kind!r}")


def eval_term(term: Term, env: Env) -> int:
    """Mirror of `Uvil.Term.eval`: the shared-theory denotation (floored
    div/mod - equal to SMT-LIB Euclidean for positive divisors)."""
    if term.op == "var":
        name = term.args[0]
        return env.get(name, 0) if isinstance(name, str) else 0
    if term.op == "const":
        value = term.args[0]
        return value if isinstance(value, int) else 0
    if term.op == "neg":
        return -eval_term(term.args[0], env)  # type: ignore[arg-type]
    a = eval_term(term.args[0], env)  # type: ignore[arg-type]
    b = eval_term(term.args[1], env)  # type: ignore[arg-type]
    return {
        "add": lambda: a + b,
        "sub": lambda: a - b,
        "mul": lambda: a * b,
        "intdiv": lambda: a // b,
        "mod": lambda: a % b,
    }[term.op]()


# --- s-expression data format (consumed by uvil-translate-prove) --------------------


def to_sexpr(term: Term) -> str:
    """Render a Term in the s-expression fixture format the Lean runner
    parses: `(var x)`, `(const 3)`, `(add T T)`, `(sub T T)`, `(mul T T)`,
    `(neg T)`, `(div T T)`, `(mod T T)`."""
    if term.op == "var":
        name = term.args[0]
        if not isinstance(name, str):
            raise ValueError(f"malformed var term: {term!r}")
        return f"(var {name})"
    if term.op == "const":
        value = term.args[0]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"const terms in the LIA fixture format are Int: {term!r}")
        return f"(const {value})"
    op_map = {"add": "add", "sub": "sub", "mul": "mul", "intdiv": "div", "mod": "mod"}
    if term.op == "neg":
        return f"(neg {to_sexpr(term.args[0])})"  # type: ignore[arg-type]
    if term.op in op_map:
        a, b = term.args
        return f"({op_map[term.op]} {to_sexpr(a)} {to_sexpr(b)})"  # type: ignore[arg-type]
    raise ValueError(f"term outside the LIA fixture format: op={term.op!r}")


def env_line(term: Term, env: Env) -> str:
    """The `| env` fixture suffix covering exactly the term's free variables."""
    names = sorted(term_vars(term))
    return ", ".join(f"{n}={env.get(n, 0)}" for n in names)


def fixture_line(term: Term, env: Env) -> str:
    """One full fixture line for the Lean runner: `SEXPR | env`."""
    return f"{to_sexpr(term)} | {env_line(term, env)}"


def parse_env_line(env_part: str) -> Env:
    """Parse the `k=v,k2=v2` fixture suffix back into an Env (the test's own
    reading of the fixture line; the runner parses the same text)."""
    out: Env = {}
    for pair in env_part.split(","):
        pair = pair.strip()
        if not pair:
            continue
        k, v = pair.split("=")
        out[k.strip()] = int(v.strip())
    return out
