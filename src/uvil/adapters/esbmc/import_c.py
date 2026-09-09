"""C harness import: a documented, small C assertion subset -> I2/I3/I4.

The parser exists ONLY for harness obligation extraction: it lowers explicit
`assert`/`__VERIFIER_assert`/`__CPROVER_assert` calls into I4 obligations over
`uvil.core.int@1`. ESBMC itself compiles the real source (untrusted here);
nothing the checker does depends on this parser.

Documented subset (anything else is an I7 `parse` diagnostic preserving the
verbatim source line - fail loud, R3):

- straight-line code: `int` declarations (with or without initializer),
  assignments, `return`, and an optional `int main(void)` wrapper;
- nondeterministic inputs: `x = __VERIFIER_nondet_int();` (declaration
  convention; reassignment introduces a fresh symbol `x_2`, `x_3`, ...);
- `if (cond) ... [else ...]` - both branches are walked (path forking, capped
  at `MAX_PATHS` live paths; assertions downstream of a fork yield one
  obligation per live path);
- bounded `for` loops `for (int i = S; i (<|<=|>|>=) K; i(++)|--|+= L|-= L)`
  with integer-literal start/bound, unrolled exactly (cap `MAX_UNROLL`);
  each iteration's loop condition is recorded as context;
- assertion calls (the obligations); `//`/`/*...*/` comments, blank
  preprocessor lines (e.g. `#include`) are skipped;
- expressions: `int` arithmetic over locals and integer literals
  (`+ - * / %`, unary `-`), comparisons, and `&& || !` in conditions.

Documented abstraction (recorded on every artifact via `model:esbmc-goto.v1`):
sequent terms use SMT-LIB integer semantics (unbounded Int, Euclidean
`div`/`mod`) - C 32-bit wraparound is NOT modeled in the sequents; overflow,
division-by-zero, array-bounds, and pointer properties are ESBMC-internal
checks evaluated by the checker against real C semantics. Model-checking
verdicts never upgrade the sequents (see `check/esbmc.py`).

`int` is the only value type: no pointers/arrays/structs/floats, no function
calls beyond the recognized builtins, no `while`/`goto`/recursion - those
surface as I7 `parse` with the verbatim line.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...artifacts import Obligation, Program, Specification, artifact_id
from ...artifacts.base import canonical_json_bytes
from ...artifacts.diagnostic import Diagnostic, Loc
from ...artifacts.obligation import CostBudget, Sequent
from ...artifacts.spec import Contracts
from ...artifacts.terms import Term, term_vars
from ...semmodels.registry import ESBMC_GOTO_V1

C_TARGET_PROFILE = "uvil.esbmc-c@1"
DEFAULT_SOLVER_MS = 2000

_NONDET = "__VERIFIER_nondet_int"
_ASSERT_NAMES = ("assert", "__VERIFIER_assert", "__CPROVER_assert")

# Path-forking budget: more live paths than this is out of subset (fail loud).
MAX_PATHS = 256
# Bounded-for unroll budget (literal iteration count).
MAX_UNROLL = 16


class CParseError(ValueError):
    """Out-of-subset C (fail loud): message + verbatim source line."""

    def __init__(self, message: str, line_no: int, line_text: str) -> None:
        super().__init__(f"{message}\n{line_text.strip()}")
        self.message = message
        self.line_no = line_no
        self.line_text = line_text


# --- expression AST -------------------------------------------------------------------


@dataclass(frozen=True)
class ENum:
    value: int


@dataclass(frozen=True)
class EName:
    name: str
    line_no: int
    line_text: str


@dataclass(frozen=True)
class ENondet:
    pass


@dataclass(frozen=True)
class EUnOp:
    op: str  # "-" | "!"
    operand: Expr


@dataclass(frozen=True)
class EBin:
    op: str  # + - * / %  |  == != < <= > >=  |  && ||
    left: Expr
    right: Expr
    line_no: int
    line_text: str


Expr = ENum | EName | ENondet | EUnOp | EBin


# --- statement AST --------------------------------------------------------------------


@dataclass(frozen=True)
class SDecl:
    name: str
    init: Expr | None
    tok: Tok


@dataclass(frozen=True)
class SAssign:
    name: str
    rhs: Expr
    tok: Tok


@dataclass(frozen=True)
class SIf:
    cond: Expr
    then_body: list[Stmt]
    else_body: list[Stmt]
    tok: Tok


@dataclass(frozen=True)
class SFor:
    var: str
    start: int
    rel: str
    bound: int
    step: int
    body: list[Stmt]
    tok: Tok


@dataclass(frozen=True)
class SAssert:
    cond: Expr
    tok: Tok


@dataclass(frozen=True)
class SReturn:
    tok: Tok


@dataclass(frozen=True)
class SEmpty:
    pass


@dataclass(frozen=True)
class _Block:
    stmts: list[Stmt]


Stmt = SDecl | SAssign | SIf | SFor | SAssert | SReturn | SEmpty | _Block

_CMP_OPS = {"==", "!=", "<", "<=", ">", ">="}
_LOGIC_OPS = {"&&", "||"}


def _require_condition(expr: Expr) -> None:
    """Conditions are comparisons or boolean combinations of them (the subset
    has no nonzero-as-bool coercion and no bool variables)."""
    match expr:
        case EBin(op=op, left=left, right=right, line_no=line_no, line_text=line_text):
            if op in _LOGIC_OPS:
                _require_condition(left)
                _require_condition(right)
            elif op in _CMP_OPS:
                _require_value(left)
                _require_value(right)
            else:
                raise CParseError(
                    "conditions must be comparisons or boolean combinations "
                    "(&&, ||, !), not bare arithmetic",
                    line_no,
                    line_text,
                )
        case EUnOp(op="!", operand=operand):
            _require_condition(operand)
        case _:
            tok = getattr(expr, "tok", None) or expr  # best-effort location
            raise CParseError(
                "conditions must be comparisons or boolean combinations "
                "(&&, ||, !), not bare arithmetic",
                getattr(tok, "line_no", 0),
                getattr(tok, "line_text", ""),
            )


def _require_value(expr: Expr) -> None:
    """Values are `int` arithmetic; comparisons as values are out of subset
    (the sequent language has no bool variables to receive them)."""
    match expr:
        case EBin(op=op, left=left, right=right, line_no=line_no, line_text=line_text):
            if op in _CMP_OPS:
                raise CParseError(
                    "comparisons as values are outside the subset (no bool variables)",
                    line_no,
                    line_text,
                )
            _require_value(left)
            _require_value(right)
        case EUnOp(op="!"):
            raise CParseError(
                "boolean negation as a value is outside the subset (no bool variables)",
                0,
                "",
            )
        case EUnOp(operand=operand):
            _require_value(operand)
        case _:
            pass


# --- tokenizer ------------------------------------------------------------------------


@dataclass(frozen=True)
class Tok:
    kind: str  # "ident" | "int" | "str" | "punct"
    value: str
    line_no: int
    line_text: str


_PUNCT = [
    "==",
    "!=",
    "<=",
    ">=",
    "&&",
    "||",
    "++",
    "--",
    "+=",
    "-=",
    "(",
    ")",
    "{",
    "}",
    ";",
    ",",
    "<",
    ">",
    "+",
    "-",
    "*",
    "/",
    "%",
    "!",
    "=",
]


def _line_of(source: str, position: int) -> tuple[int, str]:
    line_start = source.rfind("\n", 0, position) + 1
    end = source.find("\n", position)
    end = len(source) if end < 0 else end
    return source.count("\n", 0, position) + 1, source[line_start:end]


def _tokenize(source: str) -> list[Tok]:
    tokens: list[Tok] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if source.startswith("//", i):
            i = source.find("\n", i) + 1 if "\n" in source[i:] else n
            continue
        if source.startswith("/*", i):
            j = source.find("*/", i + 2)
            if j < 0:
                line_no, line_text = _line_of(source, i)
                raise CParseError("unterminated block comment", line_no, line_text)
            i = j + 2
            continue
        if ch == "#":  # preprocessor lines (e.g. #include) are skipped
            j = source.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == '"':
            j = source.find('"', i + 1)
            if j < 0:
                line_no, line_text = _line_of(source, i)
                raise CParseError("unterminated string literal", line_no, line_text)
            line_no, line_text = _line_of(source, i)
            tokens.append(Tok("str", source[i + 1 : j], line_no, line_text))
            i = j + 1
            continue
        if ch.isdigit():
            j = i
            while j < n and source[j].isdigit():
                j += 1
            line_no, line_text = _line_of(source, i)
            tokens.append(Tok("int", source[i:j], line_no, line_text))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            line_no, line_text = _line_of(source, i)
            tokens.append(Tok("ident", source[i:j], line_no, line_text))
            i = j
            continue
        for p in _PUNCT:
            if source.startswith(p, i):
                line_no, line_text = _line_of(source, i)
                tokens.append(Tok("punct", p, line_no, line_text))
                i += len(p)
                break
        else:
            line_no, line_text = _line_of(source, i)
            raise CParseError(f"unexpected character {ch!r}", line_no, line_text)
    return tokens


# --- parser (tokens -> AST) ------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[Tok]) -> None:
        self.toks = tokens
        self.pos = 0

    def peek(self, ahead: int = 0) -> Tok | None:
        idx = self.pos + ahead
        return self.toks[idx] if idx < len(self.toks) else None

    def next(self) -> Tok:
        tok = self.peek()
        if tok is None:
            raise CParseError("unexpected end of input", 0, "")
        self.pos += 1
        return tok

    def expect_punct(self, value: str) -> Tok:
        tok = self.next()
        if tok.kind != "punct" or tok.value != value:
            raise CParseError(f"expected {value!r}, got {tok.value!r}", tok.line_no, tok.line_text)
        return tok

    def at_punct(self, *values: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "punct" and tok.value in values

    def parse_body(self, closing: str | None) -> list[Stmt]:
        """Parse statements until `}` (consumed) or end of tokens."""
        stmts: list[Stmt] = []
        while True:
            tok = self.peek()
            if tok is None:
                if closing is None:
                    return stmts
                raise CParseError("unbalanced braces: missing '}'", 0, "")
            if tok.kind == "punct" and tok.value == "}":
                if closing is None:
                    raise CParseError(
                        "statements after main's body are outside the import subset",
                        tok.line_no,
                        tok.line_text,
                    )
                self.pos += 1
                return stmts
            stmts.append(self.parse_stmt())

    def parse_stmt(self) -> Stmt:
        tok = self.next()
        if tok.kind == "punct" and tok.value == ";":
            return SEmpty()
        if tok.kind == "ident" and tok.value == "int":
            name_tok = self.next()
            if name_tok.kind != "ident":
                raise CParseError(
                    f"expected a name after 'int', got {name_tok.value!r}",
                    name_tok.line_no,
                    name_tok.line_text,
                )
            init: Expr | None = None
            if self.at_punct("="):
                self.pos += 1
                init = self.parse_value()
                _require_value(init)
            self.expect_punct(";")
            return SDecl(name=name_tok.value, init=init, tok=name_tok)
        if tok.kind == "ident" and tok.value == "return":
            if not self.at_punct(";"):
                self.parse_value()  # the return value is not part of the sequent
            self.expect_punct(";")
            return SReturn(tok=tok)
        if tok.kind == "ident" and tok.value in _ASSERT_NAMES:
            self.expect_punct("(")
            cond = self.parse_expr()
            _require_condition(cond)
            if self.at_punct(","):  # __CPROVER_assert(cond, "message")
                self.pos += 1
                msg = self.next()
                if msg.kind != "str":
                    raise CParseError(
                        "expected a string literal as __CPROVER_assert message",
                        msg.line_no,
                        msg.line_text,
                    )
            self.expect_punct(")")
            self.expect_punct(";")
            return SAssert(cond=cond, tok=tok)
        if tok.kind == "ident" and tok.value == "if":
            return self.parse_if(tok)
        if tok.kind == "ident" and tok.value == "for":
            return self.parse_for(tok)
        if tok.kind == "punct" and tok.value == "{":
            body = self.parse_body("}")
            return _Block(body)
        if tok.kind == "ident":
            name_tok = tok
            if not self.at_punct("="):
                nxt = self.peek() or name_tok
                raise CParseError(
                    f"only plain assignment is supported, got {nxt.value!r}",
                    name_tok.line_no,
                    name_tok.line_text,
                )
            self.pos += 1
            rhs = self.parse_value()
            _require_value(rhs)
            self.expect_punct(";")
            return SAssign(name=name_tok.value, rhs=rhs, tok=name_tok)
        raise CParseError(
            f"statement {tok.value!r} is outside the import subset", tok.line_no, tok.line_text
        )

    def parse_braced_or_single(self) -> list[Stmt]:
        tok = self.peek()
        if tok is not None and tok.kind == "punct" and tok.value == "{":
            self.pos += 1
            return self.parse_body("}")
        return [self.parse_stmt()]

    def parse_if(self, tok: Tok) -> Stmt:
        self.expect_punct("(")
        cond = self.parse_expr()
        _require_condition(cond)
        self.expect_punct(")")
        then_body = self.parse_braced_or_single()
        else_body: list[Stmt] = []
        if self.at_ident("else"):
            self.pos += 1
            nxt = self.peek()
            if nxt is not None and nxt.kind == "ident" and nxt.value == "if":
                else_body = [self.parse_if(self.next())]
            else:
                else_body = self.parse_braced_or_single()
        return SIf(cond=cond, then_body=then_body, else_body=else_body, tok=tok)

    def at_ident(self, value: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "ident" and tok.value == value

    def parse_for(self, tok: Tok) -> Stmt:
        self.expect_punct("(")
        if not (self.at_ident("int")):
            nxt = self.peek() or tok
            raise CParseError(
                "for-init must declare the loop variable: `int i = ...`",
                nxt.line_no,
                nxt.line_text,
            )
        self.pos += 1
        name_tok = self.next()
        if name_tok.kind != "ident":
            raise CParseError("malformed for-init", name_tok.line_no, name_tok.line_text)
        self.expect_punct("=")
        start_tok = self.next()
        if start_tok.kind != "int":
            raise CParseError(
                "for-init must start from an integer literal",
                start_tok.line_no,
                start_tok.line_text,
            )
        self.expect_punct(";")
        cond_name = self.next()
        rel_tok = self.next()
        bound_tok = self.next()
        if (
            cond_name.kind != "ident"
            or rel_tok.kind != "punct"
            or rel_tok.value not in ("<", "<=", ">", ">=")
            or bound_tok.kind != "int"
        ):
            raise CParseError(
                "for-condition must be `name (<|<=|>|>=) INT`",
                rel_tok.line_no,
                rel_tok.line_text,
            )
        self.expect_punct(";")
        step, _step_end = self.parse_step(name_tok.value)
        self.expect_punct(")")
        body = self.parse_braced_or_single()
        return SFor(
            var=name_tok.value,
            start=int(start_tok.value),
            rel=rel_tok.value,
            bound=int(bound_tok.value),
            step=step,
            body=body,
            tok=tok,
        )

    def parse_step(self, name: str) -> tuple[int, int]:
        name_tok = self.next()
        if name_tok.kind != "ident" or name_tok.value != name:
            raise CParseError(
                "for-step must update the loop variable", name_tok.line_no, name_tok.line_text
            )
        nxt = self.next()
        if nxt.kind == "punct" and nxt.value == "++":
            return 1, self.pos
        if nxt.kind == "punct" and nxt.value == "--":
            return -1, self.pos
        if nxt.kind == "punct" and nxt.value in ("+=", "-="):
            lit = self.next()
            if lit.kind != "int":
                raise CParseError(
                    "for-step requires an integer literal", lit.line_no, lit.line_text
                )
            value = int(lit.value)
            return (value if nxt.value == "+=" else -value), self.pos
        raise CParseError(
            "unsupported for-step (supported: i++, i--, i += K, i -= K)",
            nxt.line_no,
            nxt.line_text,
        )

    # expressions: || < && < ! < comparison < + - < * / % < unary - < primary

    def parse_expr(self) -> Expr:
        """Condition position: comparisons (optionally combined with &&/||/!)."""
        return self.parse_or()

    def parse_value(self) -> Expr:
        """Value position: an `int` arithmetic expression (comparisons as
        values are outside the subset - the subset has no bool variables)."""
        return self.parse_additive()

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self.at_punct("||"):
            tok = self.next()
            left = EBin(
                op="||",
                left=left,
                right=self.parse_and(),
                line_no=tok.line_no,
                line_text=tok.line_text,
            )
        return left

    def parse_and(self) -> Expr:
        left = self.parse_not()
        while self.at_punct("&&"):
            tok = self.next()
            left = EBin(
                op="&&",
                left=left,
                right=self.parse_not(),
                line_no=tok.line_no,
                line_text=tok.line_text,
            )
        return left

    def parse_not(self) -> Expr:
        if self.at_punct("!"):
            self.next()
            return EUnOp(op="!", operand=self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self) -> Expr:
        left = self.parse_additive()
        tok = self.peek()
        if (
            tok is not None
            and tok.kind == "punct"
            and tok.value in ("==", "!=", "<", "<=", ">", ">=")
        ):
            self.next()
            right = self.parse_additive()
            return EBin(
                op=tok.value, left=left, right=right, line_no=tok.line_no, line_text=tok.line_text
            )
        return left  # value-position parenthesized arithmetic, e.g. (x / 2) * 2

    def parse_additive(self) -> Expr:
        left = self.parse_multiplicative()
        while self.at_punct("+", "-"):
            tok = self.next()
            right = self.parse_multiplicative()
            left = EBin(
                op=tok.value, left=left, right=right, line_no=tok.line_no, line_text=tok.line_text
            )
        return left

    def parse_multiplicative(self) -> Expr:
        left = self.parse_unary()
        while self.at_punct("*", "/", "%"):
            tok = self.next()
            right = self.parse_unary()
            left = EBin(
                op=tok.value, left=left, right=right, line_no=tok.line_no, line_text=tok.line_text
            )
        return left

    def parse_unary(self) -> Expr:
        if self.at_punct("-"):
            self.next()
            return EUnOp(op="-", operand=self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        tok = self.next()
        if tok.kind == "int":
            return ENum(value=int(tok.value))
        if tok.kind == "ident":
            if tok.value == _NONDET:
                self.expect_punct("(")
                self.expect_punct(")")
                return ENondet()
            if self.at_punct("("):
                raise CParseError(
                    f"function calls are outside the import subset: {tok.value}(...)",
                    tok.line_no,
                    tok.line_text,
                )
            return EName(name=tok.value, line_no=tok.line_no, line_text=tok.line_text)
        if tok.kind == "punct" and tok.value == "(":
            inner = self.parse_or()
            self.expect_punct(")")
            return inner
        raise CParseError(f"unexpected token {tok.value!r}", tok.line_no, tok.line_text)


# --- interpretation (AST -> per-path terms) ---------------------------------------------


@dataclass
class _Path:
    ctx: list[Term]
    env: dict[str, Term | None]
    alive: bool = True


@dataclass
class _ObligationSite:
    goal: Term
    ctx: list[Term]
    line_no: int
    line_text: str


def _instantiate(expr: Expr, env: dict[str, Term | None]) -> Term:
    match expr:
        case ENum(value=value):
            return Term(op="const", args=[value])
        case EName(name=name, line_no=line_no, line_text=line_text):
            bound = env.get(name)
            if bound is None:
                raise CParseError(
                    f"read of undefined or uninitialized variable {name!r}"
                    + ("" if name in env else " (undeclared)"),
                    line_no,
                    line_text,
                )
            return bound
        case ENondet():
            raise CParseError(
                "__VERIFIER_nondet_int() is only supported as a full assignment RHS", 0, ""
            )
        case EUnOp(op="-", operand=operand):
            return Term(op="neg", args=[_instantiate(operand, env)])
        case EUnOp(op="!", operand=operand):
            return Term(op="not", args=[_instantiate(operand, env)])
        case EBin(op=op, left=left, right=right, line_no=line_no, line_text=line_text):
            a = _instantiate(left, env)
            b = _instantiate(right, env)
            table = {
                "+": "add",
                "-": "sub",
                "*": "mul",
                "/": "intdiv",
                "%": "mod",
                "==": "eq",
                "!=": "neq",
                "<": "lt",
                "<=": "le",
                ">": "gt",
                ">=": "ge",
                "&&": "and",
                "||": "or",
            }
            core = table.get(op)
            if core is None:  # pragma: no cover - all ops come from the parser
                raise CParseError(
                    f"operator {op!r} is outside the import subset", line_no, line_text
                )
            return Term(op=core, args=[a, b])
        case _:  # pragma: no cover - all Expr shapes are handled above
            raise AssertionError(f"unhandled expression: {expr!r}")


def _negate(t: Term) -> Term:
    """Negate a condition term (De Morgan push-through for and/or/not)."""
    if t.op == "and":
        return Term(op="or", args=[_negate(a) for a in t.args if isinstance(a, Term)])
    if t.op == "or":
        return Term(op="and", args=[_negate(a) for a in t.args if isinstance(a, Term)])
    if t.op == "not":
        inner = t.args[0]
        return inner if isinstance(inner, Term) else t
    flips = {"eq": "neq", "neq": "eq", "lt": "ge", "le": "gt", "gt": "le", "ge": "lt"}
    if t.op in flips:
        return Term(op=flips[t.op], args=list(t.args))
    raise CParseError("negating this condition shape is outside the import subset", 0, "")


class _Interpreter:
    def __init__(self) -> None:
        self.sites: list[_ObligationSite] = []
        self.nondet_counter: dict[str, int] = {}

    def exec_stmts(self, stmts: list[Stmt], paths: list[_Path]) -> None:
        for stmt in stmts:
            self.exec_stmt(stmt, paths)

    def exec_stmt(self, stmt: Stmt, paths: list[_Path]) -> None:
        match stmt:
            case SEmpty():
                return
            case SDecl(name=name, init=init, tok=tok):
                for p in paths:
                    if p.alive:
                        p.env[name] = None
                if init is None:
                    return
                if isinstance(init, ENondet):
                    for p in paths:
                        if p.alive:
                            p.env[name] = self._fresh_nondet(name)
                    return
                if _mentions_nondet(init):
                    raise CParseError(
                        "__VERIFIER_nondet_int() is only supported as a full assignment RHS",
                        tok.line_no,
                        tok.line_text,
                    )
                for p in paths:
                    if p.alive:
                        p.env[name] = _instantiate(init, p.env)
            case SAssign(name=name, rhs=rhs, tok=tok):
                for p in paths:
                    if p.alive and name not in p.env:
                        raise CParseError(
                            f"assignment to undeclared variable {name!r}",
                            tok.line_no,
                            tok.line_text,
                        )
                if isinstance(rhs, ENondet):
                    for p in paths:
                        if p.alive:
                            p.env[name] = self._fresh_nondet(name)
                    return
                if _mentions_nondet(rhs):
                    raise CParseError(
                        "__VERIFIER_nondet_int() is only supported as a full assignment RHS",
                        tok.line_no,
                        tok.line_text,
                    )
                for p in paths:
                    if p.alive:
                        p.env[name] = _instantiate(rhs, p.env)
            case SAssert(cond=cond, tok=tok):
                for p in paths:
                    if not p.alive:
                        continue
                    self.sites.append(
                        _ObligationSite(
                            goal=_instantiate(cond, p.env),
                            ctx=_dedup(p.ctx),
                            line_no=tok.line_no,
                            line_text=tok.line_text,
                        )
                    )
            case SReturn():
                for p in paths:
                    p.alive = False
            case SIf(cond=cond, then_body=then_body, else_body=else_body, tok=tok):
                self._exec_if(cond, then_body, else_body, paths, tok)
            case SFor(var=name, start=start, rel=rel, bound=bound, step=step, body=body, tok=tok):
                self._exec_for(name, start, rel, bound, step, body, paths, tok)
            case _Block(stmts=inner):
                self.exec_stmts(inner, paths)
            case _:  # pragma: no cover - all Stmt shapes are handled above
                raise AssertionError(f"unhandled statement: {stmt!r}")

    def _fresh_nondet(self, name: str) -> Term:
        count = self.nondet_counter.get(name, 0) + 1
        self.nondet_counter[name] = count
        fresh = name if count == 1 else f"{name}_{count}"
        return Term(op="var", args=[fresh])

    def _exec_if(
        self,
        cond: Expr,
        then_body: list[Stmt],
        else_body: list[Stmt],
        paths: list[_Path],
        tok: Tok,
    ) -> None:
        then_paths: list[_Path] = []
        else_paths: list[_Path] = []
        for p in paths:
            if not p.alive:
                continue
            cond_then = _instantiate(cond, p.env)
            then_paths.append(_Path(ctx=[*p.ctx, cond_then], env=dict(p.env)))
            else_paths.append(_Path(ctx=[*p.ctx, _negate(cond_then)], env=dict(p.env)))
        self.exec_stmts(then_body, then_paths)
        self.exec_stmts(else_body, else_paths)
        merged = [p for p in (*then_paths, *else_paths) if p.alive]
        paths[:] = merged
        if len(paths) > MAX_PATHS:
            raise CParseError(
                f"program exceeds the {MAX_PATHS}-path import budget",
                getattr(tok, "line_no", 0),
                getattr(tok, "line_text", ""),
            )

    def _exec_for(
        self,
        name: str,
        start: int,
        rel: str,
        bound: int,
        step: int,
        body: list[Stmt],
        paths: list[_Path],
        tok: Tok,
    ) -> None:
        iterations = _iteration_count(start, rel, bound, tok)
        cond_op = {"<": "lt", "<=": "le", ">": "gt", ">=": "ge"}[rel]
        for p in paths:
            if p.alive:
                p.env[name] = Term(op="const", args=[start])
        for _ in range(iterations):
            advanced: list[_Path] = []
            for p in paths:
                if not p.alive:
                    continue
                i_value = p.env.get(name)
                if not isinstance(i_value, Term):
                    raise CParseError(
                        f"loop variable {name!r} was clobbered (outside the import subset)",
                        tok.line_no,
                        tok.line_text,
                    )
                cond = Term(
                    op=cond_op,
                    args=[i_value, Term(op="const", args=[bound])],
                )
                inner = _Path(ctx=[*p.ctx, cond], env=dict(p.env))
                self.exec_stmts(body, [inner])
                inner.env[name] = Term(
                    op="add" if step >= 0 else "sub",
                    args=[i_value, Term(op="const", args=[abs(step)])],
                )
                advanced.append(inner)
            paths[:] = advanced
            if len(paths) > MAX_PATHS:
                raise CParseError(
                    f"program exceeds the {MAX_PATHS}-path import budget",
                    tok.line_no,
                    tok.line_text,
                )


def _dedup(ctx: list[Term]) -> list[Term]:
    """Drop duplicate context terms, preserving order (Terms are unhashable;
    dedup on canonical JSON)."""
    seen: set[str] = set()
    out: list[Term] = []
    for term in ctx:
        key = canonical_json_bytes(term.model_dump(mode="json")).decode("utf-8")
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out


def _mentions_nondet(expr: Expr) -> bool:
    match expr:
        case ENondet():
            return True
        case EUnOp(operand=operand):
            return _mentions_nondet(operand)
        case EBin(left=left, right=right):
            return _mentions_nondet(left) or _mentions_nondet(right)
        case _:
            return False


def _iteration_count(start: int, rel: str, bound: int, tok: Tok) -> int:
    count = {
        "<": bound - start,
        "<=": bound - start + 1,
        ">": start - bound,
        ">=": start - bound + 1,
    }[rel]
    count = max(count, 0)
    if count > MAX_UNROLL:
        raise CParseError(
            f"bounded-for unroll budget is {MAX_UNROLL} iterations, got {count} "
            "(larger bounds are out of the import subset)",
            tok.line_no,
            tok.line_text,
        )
    return count


# --- lowering --------------------------------------------------------------------------


@dataclass
class CHarnessImport:
    name: str
    program: Program
    spec: Specification
    obligations: list[Obligation] = field(default_factory=list)


@dataclass
class CImportResult:
    filename: str
    harnesses: list[CHarnessImport] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    @property
    def obligations(self) -> list[Obligation]:
        return [o for h in self.harnesses for o in h.obligations]


def import_c(source: str, filename: str = "input.c") -> CImportResult:
    """Import a C harness in the documented subset; returns artifacts + I7
    parse diagnostics (out-of-subset input is never silently skipped)."""
    result = CImportResult(filename=filename)
    try:
        result.harnesses.append(_lower_harness(source, filename))
    except CParseError as e:
        result.diagnostics.append(
            Diagnostic(
                obligation_ref=None,
                kind="parse",
                loc=Loc(file=filename, line=e.line_no or None),
                native_message=f"{e.message}\n{e.line_text.strip()}".strip(),
            )
        )
    return result


def _lower_harness(source: str, filename: str) -> CHarnessImport:
    tokens = _tokenize(source)
    parser = _Parser(tokens)
    # accept an optional `int main(void) { ... }` wrapper
    tok0 = tokens[0]
    if not (tok0.kind == "ident" and tok0.value == "int"):
        raise CParseError(
            "the import subset accepts a single `int main(void) { ... }` harness",
            tok0.line_no,
            tok0.line_text,
        )
    parser.pos = 1  # 'int' consumed
    name_tok = parser.next()
    if not (name_tok.kind == "ident" and name_tok.value == "main"):
        raise CParseError(
            "the import subset accepts a single `int main(void) { ... }` harness",
            name_tok.line_no,
            name_tok.line_text,
        )
    parser.expect_punct("(")
    if parser.at_ident("void"):
        parser.pos += 1
    parser.expect_punct(")")
    parser.expect_punct("{")
    stmts = parser.parse_body("}")

    interpreter = _Interpreter()
    paths = [_Path(ctx=[], env={})]
    interpreter.exec_stmts(stmts, paths)

    program = Program(
        language="c",
        source_ref=filename,
        symbol="main",
        fragment=source.strip(),
        semantics_model=ESBMC_GOTO_V1.model_id,
        notes=(
            "imported by uvil.adapters.esbmc.import_c (bounded-integer harness "
            "abstraction: unbounded Int / Euclidean div-mod sequents; C 32-bit "
            "wraparound and ESBMC-internal property checks are not modeled in "
            "the sequents)"
        ),
    )
    theories = ["uvil.core.int@1", "uvil.core.bool@1"]
    spec = Specification(
        profile=C_TARGET_PROFILE,
        theories=theories,
        semantics_model=ESBMC_GOTO_V1.model_id,
        subject="main",
        contracts=Contracts(ensures=[site.goal for site in interpreter.sites]),
    )
    spec_aid = artifact_id(spec)
    program_aid = artifact_id(program)

    obligations: list[Obligation] = []
    for site in interpreter.sites:
        names = sorted(term_vars(site.goal) | {v for c in site.ctx for v in term_vars(c)})
        obligations.append(
            Obligation(
                spec_ref=spec_aid,
                program_ref=program_aid,
                semantics_model=ESBMC_GOTO_V1.model_id,
                sequent=Sequent(
                    context=site.ctx,
                    goal=site.goal,
                    var_sorts={v: "Int" for v in names},
                ),
                theories=theories,
                target_profile=C_TARGET_PROFILE,
                status="open",
                cost_budget=CostBudget(solver_ms=DEFAULT_SOLVER_MS),
                origin_backend="esbmc-c",
            )
        )
    return CHarnessImport(name="main", program=program, spec=spec, obligations=obligations)
