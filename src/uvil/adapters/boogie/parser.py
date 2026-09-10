"""Boogie subset parser (M1).

The accepted subset is explicit; anything outside it produces a `BoogieParseError`
carrying the verbatim source line, which lowering turns into an I7 `parse`
diagnostic (fail-loud, never silently skipped).

Accepted subset:

- Declarations: `type` synonyms, `const` (optionally with a definition body),
  global `var`, `axiom`, `function` (uninterpreted or with a definition body),
  `procedure` with `requires` / `ensures` / `modifies`.
- Sorts: `int`, `bool`, `real`; array/map types `[T1, ..., Tn]T` (mapped to
  `uvil.core.array`); sequence types `seq<T>` (mapped to `uvil.core.seq`).
- Statements: `assume`, `assert` (including `assert E by { ... }`), single
  assignments `x := E;` / `a[i] := v;`, `havoc x[, y];`, `while G invariant I.. {..}`,
  `return;`, and body-local `var x: T;` declarations.
- Expressions: literals, identifiers, `old(x)`, arithmetic (`+ - * / div mod`),
  comparisons (`== != < <= > >=`), boolean connectives (`&& || ! ==> <==`),
  `if c then a else b` terms, array select/store (`a[i]`, `a[i := v]`),
  sequence length/index (`|s|`, `s[i]`), and quantifiers
  `forall/exists x: T :: {triggers} E` (trigger sets are parsed and ignored).
- Comments: `//`, `/* */`. Attributes `{:...}` are parsed and ignored.

This module is syntax only: the verification conditions are computed by
`vcgen.py` (sound WP, `origin_backend="boogie-wp"`, ADR 0008).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...artifacts.terms import Term, TermArg

BOOGIE_TARGET_PROFILE = "uvil.boogie@1"


class BoogieParseError(Exception):
    """Raised for anything outside the documented subset; carries the verbatim line."""

    def __init__(self, message: str, line_no: int, line_text: str) -> None:
        super().__init__(f"line {line_no}: {message}")
        self.message = message
        self.line_no = line_no
        self.line_text = line_text


@dataclass(frozen=True)
class BoogieType:
    """A Boogie type from the subset: scalar, array `[T1..Tn]T`, seq<T>, or synonym."""

    sort: str  # "int" | "bool" | "real" | "array" | "seq" | synonym name
    params: tuple[BoogieType, ...] = ()

    def smt_sort(self) -> str:
        if self.sort == "int":
            return "Int"
        if self.sort == "bool":
            return "Bool"
        if self.sort == "real":
            return "Real"
        if self.sort == "seq":
            return f"(Seq {self.params[0].smt_sort()})"
        if self.sort == "array":
            domain = " ".join(p.smt_sort() for p in self.params[:-1])
            return f"(Array {domain} {self.params[-1].smt_sort()})"
        raise BoogieSortError(f"unresolved type synonym: {self.sort!r}")

    def theory(self) -> str:
        if self.sort == "int":
            return "uvil.core.int@1"
        if self.sort == "bool":
            return "uvil.core.bool@1"
        if self.sort == "real":
            return "uvil.core.real@1"
        if self.sort == "seq":
            return "uvil.core.seq@1"
        if self.sort == "array":
            return "uvil.core.array@1"
        raise BoogieSortError(f"unresolved type synonym: {self.sort!r}")


class BoogieSortError(Exception):
    pass


@dataclass(frozen=True)
class Param:
    name: str
    type: BoogieType


@dataclass
class ConstDecl:
    name: str
    type: BoogieType
    definition: Term | None = None


@dataclass
class VarDecl:
    name: str
    type: BoogieType


@dataclass
class AxiomDecl:
    name: str | None
    term: Term


@dataclass
class FunctionDecl:
    name: str
    params: list[Param]
    return_type: BoogieType
    body: Term | None = None


@dataclass
class AssumeStmt:
    term: Term


@dataclass
class AssertStmt:
    term: Term
    by_body: list[Stmt] = field(default_factory=list)


@dataclass
class AssignStmt:
    target: str | tuple[str, Term]  # plain var, or (array_name, index_term)
    term: Term


@dataclass
class HavocStmt:
    names: list[str]


@dataclass
class WhileStmt:
    guard: Term
    invariants: list[Term]
    body: list[Stmt]


@dataclass
class VarStmt:
    name: str
    type: BoogieType


@dataclass
class ReturnStmt:
    pass


Stmt = AssumeStmt | AssertStmt | AssignStmt | HavocStmt | WhileStmt | VarStmt | ReturnStmt


@dataclass
class ProcedureDecl:
    name: str
    params: list[Param]
    returns: list[Param]
    requires: list[Term]
    ensures: list[Term]
    modifies: list[str]
    body: list[Stmt]
    source_span: tuple[int, int] = (0, 0)  # char offsets into the module source


@dataclass
class BoogieModule:
    name: str
    type_aliases: dict[str, BoogieType]
    consts: list[ConstDecl]
    vars: list[VarDecl]
    axioms: list[AxiomDecl]
    functions: list[FunctionDecl]
    procedures: list[ProcedureDecl]


@dataclass
class ParseOutcome:
    module: BoogieModule | None
    errors: list[BoogieParseError]

    @property
    def ok(self) -> bool:
        return self.module is not None and not self.errors


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
    | (?P<comment>//[^\n]*|/\*.*?\*/)
    | (?P<attr>\{:[^{}]*\})
    | (?P<num>\d+\.\d+|\d+)
    | (?P<id>[A-Za-z_$][A-Za-z0-9_$']*)
    | (?P<op>==>|<==|==|!=|<=|>=|&&|\|\||:=|::|[-+*/%<>!:;,(){}\[\]=|.@?])
    """,
    re.VERBOSE | re.DOTALL,
)

_KEYWORDS = {
    "type",
    "const",
    "var",
    "axiom",
    "function",
    "procedure",
    "requires",
    "ensures",
    "modifies",
    "returns",
    "free",
    "assume",
    "assert",
    "havoc",
    "while",
    "invariant",
    "by",
    "if",
    "then",
    "else",
    "forall",
    "exists",
    "div",
    "mod",
    "old",
    "return",
    "true",
    "false",
}


class Token:
    __slots__ = ("char_start", "kind", "line_no", "line_text", "text")

    def __init__(self, kind: str, text: str, line_no: int, line_text: str, char_start: int) -> None:
        self.kind = kind
        self.text = text
        self.line_no = line_no
        self.line_text = line_text
        self.char_start = char_start

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind!r}, {self.text!r}, line {self.line_no})"


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    line_no = 1
    line_start = 0
    n = len(source)
    while pos < n:
        start = pos
        m = _TOKEN_RE.match(source, pos)
        if m is None:
            line_text = source[line_start:].split("\n", 1)[0]
            raise BoogieParseError(
                f"unexpected character {source[pos]!r} outside the accepted subset",
                line_no,
                line_text,
            )
        kind = m.lastgroup or ""
        text = m.group()
        if kind == "comment" or kind == "attr":
            pass
        elif kind != "ws":
            tokens.append(Token(kind, text, line_no, source[line_start:].split("\n", 1)[0], start))
        line_no += text.count("\n")
        if "\n" in text:
            line_start = source.rfind("\n", pos, pos + len(text)) + 1
        pos = m.end()
    return tokens


class Parser:
    def __init__(self, source: str, name: str = "module") -> None:
        self.source = source
        self.name = name
        self.tokens = tokenize(source)
        self.pos = 0
        self.scopes: list[dict[str, BoogieType]] = [{}]
        self.aliases: dict[str, BoogieType] = {}

    # -- token helpers ------------------------------------------------------

    def peek(self, offset: int = 0) -> Token | None:
        i = self.pos + offset
        return self.tokens[i] if i < len(self.tokens) else None

    def error(self, message: str) -> BoogieParseError:
        tok = self.peek()
        if tok is None:
            lines = self.source.splitlines()
            line_no = len(lines)
            line_text = lines[-1] if lines else ""
        else:
            line_no, line_text = tok.line_no, tok.line_text
        return BoogieParseError(message, line_no, line_text)

    def at(self, text: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.text == text

    def at_keyword(self, keyword: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "id" and tok.text == keyword

    def accept(self, text: str) -> Token | None:
        if self.at(text):
            tok = self.tokens[self.pos]
            self.pos += 1
            return tok
        return None

    def expect(self, text: str) -> Token:
        tok = self.accept(text)
        if tok is None:
            found = self.peek()
            found_text = found.text if found else "<eof>"
            raise self.error(f"expected {text!r}, found {found_text!r}")
        return tok

    def expect_identifier(self) -> str:
        tok = self.peek()
        if tok is None or tok.kind != "id":
            raise self.error("expected identifier")
        self.pos += 1
        return tok.text

    def expect_keyword(self, keyword: str) -> None:
        tok = self.peek()
        if tok is None or tok.kind != "id" or tok.text != keyword:
            found = tok.text if tok else "<eof>"
            raise self.error(f"expected {keyword!r}, found {found!r}")
        self.pos += 1

    # -- scope helpers ------------------------------------------------------

    def declare(self, name: str, boogie_type: BoogieType) -> None:
        self.scopes[-1][name] = boogie_type

    def lookup(self, name: str) -> BoogieType | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    # -- module -------------------------------------------------------------

    def parse_module(self) -> BoogieModule:
        consts: list[ConstDecl] = []
        gvars: list[VarDecl] = []
        axioms: list[AxiomDecl] = []
        functions: list[FunctionDecl] = []
        procedures: list[ProcedureDecl] = []
        while self.peek() is not None:
            if self.at_keyword("type"):
                self._parse_type_synonym()
            elif self.at_keyword("const"):
                consts.append(self._parse_const())
            elif self.at_keyword("var"):
                gvars.extend(self._parse_var_decls())
            elif self.at_keyword("axiom"):
                axioms.append(self._parse_axiom())
            elif self.at_keyword("function"):
                functions.append(self._parse_function())
            elif self.at_keyword("procedure"):
                procedures.append(self._parse_procedure())
            else:
                tok = self.peek()
                raise self.error(
                    f"declaration {tok.text!r} is outside the accepted subset"
                    if tok
                    else "unexpected end of input"
                )
        return BoogieModule(
            name=self.name,
            type_aliases=self.aliases,
            consts=consts,
            vars=gvars,
            axioms=axioms,
            functions=functions,
            procedures=procedures,
        )

    def _resolve_type(self, boogie_type: BoogieType) -> BoogieType:
        if boogie_type.sort in self.aliases:
            return self.aliases[boogie_type.sort]
        return boogie_type

    def _parse_type_synonym(self) -> None:
        self.expect_keyword("type")
        name = self.expect_identifier()
        self.expect("=")
        boogie_type = self._parse_type()
        self.expect(";")
        self.aliases[name] = boogie_type

    def _parse_type(self) -> BoogieType:
        tok = self.peek()
        if tok is None:
            raise self.error("expected a type")
        if tok.text == "[":
            self.expect("[")
            params: list[BoogieType] = [self._parse_type()]
            while self.accept(","):
                params.append(self._parse_type())
            self.expect("]")
            params.append(self._parse_type())
            return BoogieType(sort="array", params=tuple(params))
        if tok.kind != "id":
            raise self.error(f"unexpected token {tok.text!r} in type position")
        self.pos += 1
        name = tok.text
        if name == "int":
            return BoogieType(sort="int")
        if name == "bool":
            return BoogieType(sort="bool")
        if name == "real":
            return BoogieType(sort="real")
        if name in self.aliases:
            return self.aliases[name]
        if name == "seq":
            self.expect("<")
            elem = self._parse_type()
            self.expect(">")
            return BoogieType(sort="seq", params=(elem,))
        raise self.error(
            f"type {name!r} is outside the accepted subset (use int/bool/real/[T]T/seq<T>)"
        )

    def _parse_const(self) -> ConstDecl:
        self.expect_keyword("const")
        name = self.expect_identifier()
        self.expect(":")
        boogie_type = self._resolve_type(self._parse_type())
        definition: Term | None = None
        if self.accept(":=") or self.accept("="):
            definition = self._parse_expr()
        self.expect(";")
        self.scopes[0][name] = boogie_type
        return ConstDecl(name=name, type=boogie_type, definition=definition)

    def _parse_var_decls(self) -> list[VarDecl]:
        self.expect_keyword("var")
        decls: list[VarDecl] = []
        while True:
            name = self.expect_identifier()
            self.expect(":")
            boogie_type = self._resolve_type(self._parse_type())
            decls.append(VarDecl(name=name, type=boogie_type))
            if not self.accept(","):
                break
        self.expect(";")
        target = self.scopes[0] if len(self.scopes) == 1 else self.scopes[-1]
        for d in decls:
            target[d.name] = d.type
        return decls

    def _parse_axiom(self) -> AxiomDecl:
        self.expect_keyword("axiom")
        name: str | None = None
        # optional label form: `axiom A: E;`
        tok = self.peek()
        nxt = self.peek(1)
        labeled = (
            tok is not None
            and tok.kind == "id"
            and tok.text not in _KEYWORDS
            and nxt is not None
            and nxt.text == ":"
        )
        if labeled and tok is not None:
            name = tok.text
            self.pos += 2  # consume `name` and `:`
        term = self._parse_expr()
        self.expect(";")
        return AxiomDecl(name=name, term=term)

    def _parse_function(self) -> FunctionDecl:
        self.expect_keyword("function")
        name = self.expect_identifier()
        params: list[Param] = []
        if self.accept("("):
            params = self._parse_param_list(")")
            self.expect(")")
        self.expect_keyword("returns")
        self.expect("(")
        returns = self._parse_param_list(")")
        self.expect(")")
        body: Term | None = None
        if self.accept("{"):
            body = self._parse_expr()
            self.expect("}")
        else:
            self.expect(";")
        return FunctionDecl(name=name, params=params, return_type=returns[0].type, body=body)

    def _parse_param_list(self, _end: str) -> list[Param]:
        params: list[Param] = []
        while not self.at(")"):
            tok = self.peek()
            nxt = self.peek(1)
            named = (
                tok is not None
                and tok.kind == "id"
                and tok.text not in _KEYWORDS - {"int", "bool", "real"}
                and nxt is not None
                and nxt.text == ":"
            )
            if not named:
                # anonymous type entry, e.g. `returns (int)`
                boogie_type = self._resolve_type(self._parse_type())
                params.append(Param(name=f"__ret{len(params)}", type=boogie_type))
            else:
                group: list[str] = [self.expect_identifier()]
                while self.accept(","):
                    group.append(self.expect_identifier())
                self.expect(":")
                boogie_type = self._resolve_type(self._parse_type())
                for g in group:
                    params.append(Param(name=g, type=boogie_type))
                    self.declare(g, boogie_type)
            if not (self.accept(";") or self.accept(",")) and not self.at(")"):
                break
        return params

    def _parse_procedure(self) -> ProcedureDecl:
        self.expect_keyword("procedure")
        span_start = self.tokens[self.pos - 1].char_start
        name = self.expect_identifier()
        self.scopes.append({})
        params: list[Param] = []
        if self.accept("("):
            params = self._parse_param_list(")")
            self.expect(")")
        returns: list[Param] = []
        if self.at_keyword("returns"):
            self.expect_keyword("returns")
            self.expect("(")
            returns = self._parse_param_list(")")
            self.expect(")")
        requires: list[Term] = []
        ensures: list[Term] = []
        modifies: list[str] = []
        while self.peek() is not None and (
            self.at_keyword("requires")
            or self.at_keyword("ensures")
            or self.at_keyword("modifies")
            or self.at_keyword("free")
        ):
            if self._accept_keyword("free") or self.at_keyword("requires"):
                self.expect_keyword("requires")
                requires.append(self._parse_expr())
                self.accept(";")
            elif self.at_keyword("ensures"):
                self.expect_keyword("ensures")
                ensures.append(self._parse_expr())
                self.accept(";")
            else:
                self.expect_keyword("modifies")
                modifies.append(self.expect_identifier())
                while self.accept(","):
                    modifies.append(self.expect_identifier())
                self.accept(";")
        body: list[Stmt] = []
        if self.accept("{"):
            body = self._parse_block()
        span_end = self.tokens[self.pos - 1].char_start + len(self.tokens[self.pos - 1].text)
        self.scopes.pop()
        return ProcedureDecl(
            name=name,
            params=params,
            returns=returns,
            requires=requires,
            ensures=ensures,
            modifies=modifies,
            body=body,
            source_span=(span_start, span_end),
        )

    def _accept_keyword(self, keyword: str) -> bool:
        if self.at_keyword(keyword):
            self.pos += 1
            return True
        return False

    def _parse_block(self) -> list[Stmt]:
        stmts: list[Stmt] = []
        while not self.at("}"):
            tok = self.peek()
            if tok is None:
                raise self.error("unexpected end of input inside block")
            stmts.extend(self._parse_statement())
        self.expect("}")
        return stmts

    def _parse_statement(self) -> list[Stmt]:
        tok = self.peek()
        if tok is None:
            raise self.error("unexpected end of input")
        nxt = self.peek(1)
        labeled = (
            tok.kind == "id" and tok.text not in _KEYWORDS and nxt is not None and nxt.text == ":"
        )
        if labeled:
            self.pos += 2  # label - parsed and ignored
            return self._parse_statement()
        if self.at_keyword("assume"):
            self.expect_keyword("assume")
            term = self._parse_expr()
            self.expect(";")
            return [AssumeStmt(term=term)]
        if self.at_keyword("assert"):
            return [self._parse_assert()]
        if self.at_keyword("havoc"):
            self.expect_keyword("havoc")
            names = [self.expect_identifier()]
            while self.accept(","):
                names.append(self.expect_identifier())
            self.expect(";")
            return [HavocStmt(names=names)]
        if self.at_keyword("while"):
            return [self._parse_while()]
        if self.at_keyword("if"):
            raise self.error("'if' is outside the accepted M1 subset (straight-line + while only)")
        if self.at_keyword("call"):
            raise self.error("procedure calls are outside the accepted M1 subset")
        if self.at_keyword("return"):
            self.expect_keyword("return")
            self.expect(";")
            return [ReturnStmt()]
        if self.at_keyword("var"):
            decls = self._parse_var_decls()
            return [VarStmt(name=d.name, type=d.type) for d in decls]
        # assignment: `x := E;` or `a[i] := v;`
        target = self.expect_identifier()
        if self.accept("["):
            index = self._parse_expr()
            self.expect("]")
            self.expect(":=")
            value = self._parse_expr()
            self.expect(";")
            return [AssignStmt(target=(target, index), term=value)]
        self.expect(":=")
        value = self._parse_expr()
        self.expect(";")
        return [AssignStmt(target=target, term=value)]

    def _parse_assert(self) -> AssertStmt:
        self.expect_keyword("assert")
        term = self._parse_expr()
        by_body: list[Stmt] = []
        if self.at_keyword("by"):
            self.expect_keyword("by")
            self.expect("{")
            by_body = self._parse_block()
        else:
            self.expect(";")
        return AssertStmt(term=term, by_body=by_body)

    def _parse_while(self) -> WhileStmt:
        self.expect_keyword("while")
        guard = self._parse_expr()
        invariants: list[Term] = []
        while self.at_keyword("invariant"):
            self.expect_keyword("invariant")
            invariants.append(self._parse_expr())
            self.accept(";")
        if not self.accept("{"):
            raise self.error("while loop body must be braced in the accepted subset")
        body = self._parse_block()
        return WhileStmt(guard=guard, invariants=invariants, body=body)

    # -- expressions --------------------------------------------------------

    def _parse_expr(self) -> Term:
        return self._parse_implies()

    def _parse_implies(self) -> Term:
        left = self._parse_or()
        if self.at("==>"):
            self.expect("==>")
            right = self._parse_implies()  # right-associative
            return Term(op="implies", args=[left, right])
        if self.at("<=="):
            self.expect("<==")
            right = self._parse_implies()
            return Term(op="implies", args=[right, left])
        return left

    def _parse_or(self) -> Term:
        terms: list[TermArg] = [self._parse_and()]
        while self.at("||"):
            self.expect("||")
            terms.append(self._parse_and())
        if len(terms) == 1 and isinstance(terms[0], Term):
            return terms[0]
        return Term(op="or", args=terms)

    def _parse_and(self) -> Term:
        terms: list[TermArg] = [self._parse_relational()]
        while self.at("&&"):
            self.expect("&&")
            terms.append(self._parse_relational())
        if len(terms) == 1 and isinstance(terms[0], Term):
            return terms[0]
        return Term(op="and", args=terms)

    def _parse_relational(self) -> Term:
        left = self._parse_additive()
        for op_text, core_op in (
            ("==", "eq"),
            ("!=", "neq"),
            ("<", "lt"),
            ("<=", "le"),
            (">", "gt"),
            (">=", "ge"),
        ):
            if self.at(op_text):
                self.expect(op_text)
                right = self._parse_additive()
                return Term(op=core_op, args=[left, right])
        return left

    def _parse_additive(self) -> Term:
        result = self._parse_multiplicative()
        while self.at("+") or self.at("-"):
            plus = self.at("+")
            self.pos += 1
            rhs = self._parse_multiplicative()
            op = "add" if plus else "sub"
            result = Term(op=op, args=[result, rhs])
        return result

    def _parse_multiplicative(self) -> Term:
        left = self._parse_unary()
        while True:
            if self.at("*"):
                self.expect("*")
                left = Term(op="mul", args=[left, self._parse_unary()])
            elif self.at("/"):
                self.expect("/")
                right = self._parse_unary()
                left = Term(op=self._div_op(left, right), args=[left, right])
            elif self.at("%") or self.at_keyword("mod"):
                if self.at("%"):
                    self.expect("%")
                else:
                    self.expect_keyword("mod")
                left = Term(op="mod", args=[left, self._parse_unary()])
            elif self.at_keyword("div"):
                self.expect_keyword("div")
                left = Term(op="intdiv", args=[left, self._parse_unary()])
            else:
                return left

    def _div_op(self, left: Term, right: Term) -> str:
        lt = self._term_sort_guess(left)
        rt = self._term_sort_guess(right)
        if lt == "real" or rt == "real":
            return "realdiv"
        return "intdiv"

    def _term_sort_guess(self, term: Term) -> str:
        if term.op == "var" and term.args and isinstance(term.args[0], str):
            found = self.lookup(term.args[0])
            if found is not None:
                return found.sort
        return "int"

    def _parse_unary(self) -> Term:
        if self.accept("-"):
            return Term(op="neg", args=[self._parse_unary()])
        if self.accept("!"):
            return Term(op="not", args=[self._parse_unary()])
        if self.at("|"):
            self.expect("|")
            inner = self._parse_expr()
            self.expect("|")
            return Term(op="seq.len", args=[inner])
        return self._parse_postfix()

    def _parse_postfix(self) -> Term:
        term = self._parse_primary()
        while True:
            if self.at("["):
                self.expect("[")
                if self.accept("]"):  # unsupported slice forms
                    raise self.error("empty index is outside the accepted subset")
                index = self._parse_expr()
                if self.accept(":="):
                    value = self._parse_expr()
                    self.expect("]")
                    term = Term(op=self._update_op(term), args=[term, index, value])
                else:
                    self.expect("]")
                    term = self._index_term(term, index)
            else:
                return term

    def _expr_sort(self, term: Term) -> str | None:
        """Lightweight sort propagation for collection operators (M1 inference)."""
        if term.op == "var" and term.args and isinstance(term.args[0], str):
            found = self.lookup(term.args[0])
            return found.sort if found is not None else None
        if term.op in ("seq.update", "seq.nth", "seq.cons", "seq.empty"):
            return "seq"
        if term.op in ("select", "store"):
            return "array"
        return None

    def _update_op(self, base: Term) -> str:
        return "seq.update" if self._expr_sort(base) == "seq" else "store"

    def _index_term(self, base: Term, index: Term) -> Term:
        if self._expr_sort(base) == "seq":
            return Term(op="seq.nth", args=[base, index])
        return Term(op="select", args=[base, index])

    def _parse_primary(self) -> Term:
        tok = self.peek()
        if tok is None:
            raise self.error("unexpected end of input in expression")
        if tok.text == "(":
            self.expect("(")
            term = self._parse_expr()
            self.expect(")")
            return term
        if tok.kind == "num":
            self.pos += 1
            if "." in tok.text:
                return Term(op="const", args=[float(tok.text)])
            return Term(op="const", args=[int(tok.text)])
        if tok.kind != "id":
            raise self.error(f"expression token {tok.text!r} is outside the accepted subset")
        if tok.text == "true":
            self.pos += 1
            return Term(op="const", args=[True])
        if tok.text == "false":
            self.pos += 1
            return Term(op="const", args=[False])
        if tok.text == "old":
            self.pos += 1
            self.expect("(")
            inner = self.expect_identifier()
            self.expect(")")
            return Term(op="var", args=[f"old({inner})"])
        if tok.text == "forall" or tok.text == "exists":
            return self._parse_quantifier(tok.text)
        if tok.text == "if":
            self.pos += 1
            cond = self._parse_expr()
            self.expect_keyword("then")
            then_e = self._parse_expr()
            self.expect_keyword("else")
            else_e = self._parse_expr()
            return Term(op="ite", args=[cond, then_e, else_e])
        # identifier, possibly a function call
        self.pos += 1
        name = tok.text
        if self.at("("):
            self.expect("(")
            args: list[TermArg] = [name]
            if not self.at(")"):
                args.append(self._parse_expr())
                while self.accept(","):
                    args.append(self._parse_expr())
            self.expect(")")
            return Term(op="call", args=args)
        found = self.lookup(name)
        if found is None:
            raise self.error(f"unknown identifier {name!r} (not declared in the accepted subset)")
        return Term(op="var", args=[name])

    def _parse_quantifier(self, which: str) -> Term:
        self.pos += 1  # forall / exists
        bound: list[tuple[str, BoogieType]] = []
        while True:
            name = self.expect_identifier()
            self.expect(":")
            boogie_type = self._resolve_type(self._parse_type())
            bound.append((name, boogie_type))
            if not self.accept(","):
                break
        if self.at("{"):
            self._skip_trigger_set()
        self.expect("::")
        self.scopes.append(dict(bound))
        body = self._parse_expr()
        self.scopes.pop()
        result = body
        for name, boogie_type in reversed(bound):
            result = Term(op=which, args=[name, boogie_type.smt_sort(), result])
        return result

    def _skip_trigger_set(self) -> None:
        self.expect("{")
        depth = 1
        while depth > 0:
            tok = self.peek()
            if tok is None:
                raise self.error("unterminated trigger set")
            if tok.text == "{":
                depth += 1
            elif tok.text == "}":
                depth -= 1
            self.pos += 1


def parse_module(source: str, name: str = "module") -> BoogieModule:
    """Strict API: parse the whole module, raising on the first out-of-subset construct."""
    return Parser(source, name).parse_module()


def parse_module_tolerant(source: str, name: str = "module") -> ParseOutcome:
    """Recover per procedure: parse declarations and procedures, isolating errors.

    A procedure that fails to parse is skipped *loudly*: its error is returned in
    `ParseOutcome.errors` and lowering turns it into an I7 diagnostic. Declarations
    preceding a broken procedure are still collected.
    """
    parser = Parser(source, name)
    errors: list[BoogieParseError] = []
    consts: list[ConstDecl] = []
    gvars: list[VarDecl] = []
    axioms: list[AxiomDecl] = []
    functions: list[FunctionDecl] = []
    procedures: list[ProcedureDecl] = []
    while parser.peek() is not None:
        try:
            if parser.at_keyword("type"):
                parser._parse_type_synonym()
            elif parser.at_keyword("const"):
                consts.append(parser._parse_const())
            elif parser.at_keyword("var"):
                gvars.extend(parser._parse_var_decls())
            elif parser.at_keyword("axiom"):
                axioms.append(parser._parse_axiom())
            elif parser.at_keyword("function"):
                functions.append(parser._parse_function())
            elif parser.at_keyword("procedure"):
                procedures.append(parser._parse_procedure())
            else:
                tok = parser.peek()
                raise parser.error(
                    f"declaration {tok.text!r} is outside the accepted subset"
                    if tok
                    else "unexpected end of input"
                )
        except BoogieParseError as e:
            errors.append(e)
            if parser.at_keyword("procedure"):
                continue
            # skip to the next procedure to recover
            while parser.peek() is not None and not parser.at_keyword("procedure"):
                parser.pos += 1
    module = BoogieModule(
        name=name,
        type_aliases=parser.aliases,
        consts=consts,
        vars=gvars,
        axioms=axioms,
        functions=functions,
        procedures=procedures,
    )
    return ParseOutcome(module=module, errors=errors)
