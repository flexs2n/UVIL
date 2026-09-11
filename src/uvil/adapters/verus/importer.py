"""Verus import adapter: Verus/Rust artifacts (.rs) -> I2/I3/I4.

**Vendor-TCB caveat (recorded in every artifact this adapter produces):**
Verus (github.com/verus-lang/verus) generates its own VCs and dispatches
them to its own z3; UVIL consumes its artifacts as a FRONTEND, not a
neutral peer. Imported obligations are ordinary I4s: any guarantee they
carry must come from UVIL's own backends (`uvil check` re-dispatches the
shared-subset sequents through the pinned z3 - solver-verdict G1), never
from the vendor pipeline. Native Verus run records (the ground-truth arm
of the VeriContest harvest) are run records in `corpora/vericontest/
expected.json`, never I5 proofs - the native verdict is the thing being
COMPARED against, not trusted.

Pinned by release tag + commit (ADR 0002 discipline): PINNED_VERUS_TAG +
PINNED_VERUS_COMMIT + recorded rust toolchain.

The import subset is discovered against the committed VeriContest corpus
(`corpora/vericontest/upstream/`, verbatim): `verus! { }` blocks containing
`fn` procedures with scalar `i*`/`u*`/`bool` parameters, `requires`/`ensures`
clauses, and straight-line bodies (`let`/assignment/`assert`; an empty body
is the degenerate straight-line case - the post-state equals the entry
state). Spec expressions are the LIA surface the harnesses exercise
(literals with `int` widening suffix, comparisons, `&&`/`||`/`!`, `+ - * /
%`, unary `-`). Anything else fails loud as I7: `spec fn`/`proof fn`/
`recommends`/`decreases` and quantifier/Seq/Vec/struct fragments surface as
I7 `semantic-mismatch`; loops, `if`, indexing, method calls, `match`, and
non-scalar types surface as I7 `parse` - all with the verbatim line. The
sequents are UNBOUNDED-Int/Euclidean div-mod over `uvil.core.int@1` (the
ESBMC harness-abstraction precedent): Verus's bounded two's-complement
machine semantics are intentionally NOT modeled, which is exactly why the
native verdict never upgrades an imported obligation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ...artifacts import Obligation, Program, Specification, artifact_id
from ...artifacts.diagnostic import Diagnostic, Loc
from ...artifacts.obligation import CostBudget, Sequent
from ...artifacts.spec import Contracts
from ...artifacts.terms import Term, term_vars
from ...semmodels.registry import VERUS_SUBSET_V1
from ..boogie.lower import ImportResult, ProcedureImport  # the common core shapes

VERUS_TARGET_PROFILE = "uvil.verus-subset@1"
DEFAULT_SOLVER_MS = 2000

VERUS_REPO = "https://github.com/verus-lang/verus"
PINNED_VERUS_TAG = "release/0.2026.09.06.8dea4a2"
PINNED_VERUS_COMMIT = "8dea4a2196ebf99449fe2f141a2fb30acae3f17c"
PINNED_VERUS_TOOLCHAIN = "1.98.0-x86_64-pc-windows-msvc"
PINNED_VERUS_Z3 = "4.16.0"

_IN_SUBSET_TYPES = {
    "i8": "int",
    "i16": "int",
    "i32": "int",
    "i64": "int",
    "i128": "int",
    "isize": "int",
    "u8": "int",
    "u16": "int",
    "u32": "int",
    "u64": "int",
    "u128": "int",
    "usize": "int",
    "bool": "bool",
}


class VerusImportError(ValueError):
    """Out-of-subset Verus artifact (fail loud): message + verbatim line."""

    def __init__(self, kind: str, message: str, line_no: int, line_text: str) -> None:
        super().__init__(f"{message}\n{line_text.strip()}")
        self.kind = kind
        self.message = message
        self.line_no = line_no
        self.line_text = line_text


def _line_of(source: str, position: int) -> tuple[int, str]:
    line_no = source.count("\n", 0, position) + 1
    line_start = source.rfind("\n", 0, position) + 1
    line_end = source.find("\n", position)
    if line_end < 0:
        line_end = len(source)
    return line_no, source[line_start:line_end]


# --- tokenizer -----------------------------------------------------------------------


@dataclass
class Tok:
    kind: str  # ident | number | punct
    value: str
    pos: int
    line_no: int = 0
    line_text: str = ""


def _tokenize(source: str, start: int, end: int) -> list[Tok]:
    """Tokenize source[start:end]; Rust line/block comments are stripped."""
    toks: list[Tok] = []
    i = start
    while i < end:
        c = source[i]
        if c in " \t\r\n":
            i += 1
            continue
        if source.startswith("//", i):
            j = source.find("\n", i)
            i = end if j < 0 else j + 1
            continue
        if source.startswith("/*", i):
            j = source.find("*/", i + 2)
            if j < 0 or j >= end:
                i = end
            else:
                i = j + 2
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            while j < end and (source[j].isalnum() or source[j] == "_"):
                j += 1
            toks.append(Tok("ident", source[i:j], i))
            i = j
            continue
        if c.isdigit():
            j = i + 1
            while j < end and (source[j].isalnum() or source[j] == "_"):
                j += 1
            toks.append(Tok("number", source[i:j], i))
            i = j
            continue
        for two in ("==", "!=", "<=", ">=", "&&", "||", "->", "::"):
            if source.startswith(two, i):
                toks.append(Tok("punct", two, i))
                i += 2
                break
        else:
            toks.append(Tok("punct", c, i))
            i += 1
    for tok in toks:
        (tok.line_no, tok.line_text) = _line_of(source, tok.pos)
    return toks


def _strip_int_suffix(raw: str) -> int:
    """Rust integer literal with optional `int` widening suffix (spec mode);
    digit separators `_` are ignored."""
    digits = raw
    suffix = ""
    k = 0
    while k < len(raw) and (raw[k].isdigit() or raw[k] == "_"):
        k += 1
    digits, suffix = raw[:k], raw[k:]
    if suffix and suffix != "int":
        raise ValueError(f"unsupported literal suffix {suffix!r}")
    value = int(digits.replace("_", ""))
    return value


# --- expression parser (the LIA spec surface) ----------------------------------------


class _ExprParser:
    """Precedence parser over the in-subset expression surface; produces the
    shared `Term` shapes (the same nodes the Strata importer emits)."""

    def __init__(self, tokens: list[Tok], pos: int) -> None:
        self._toks = tokens
        self._pos = pos

    def peek(self) -> Tok | None:
        return self._toks[self._pos] if self._pos < len(self._toks) else None

    def next(self) -> Tok:
        tok = self.peek()
        if tok is None:
            raise VerusImportError("parse", "unexpected end of input", 0, "")
        self._pos += 1
        return tok

    def at_punct(self, *values: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "punct" and tok.value in values

    def expect(self, value: str) -> Tok:
        tok = self.next()
        if not (tok.kind == "punct" and tok.value == value):
            raise VerusImportError(
                "parse", f"expected {value!r}, got {tok.value!r}", tok.line_no, tok.line_text
            )
        return tok

    def fail_out_of_subset(self, tok: Tok, why: str) -> VerusImportError:
        return VerusImportError("semantic-mismatch", why, tok.line_no, tok.line_text)

    def parse(self) -> Term:
        return self._or()

    def _or(self) -> Term:
        left = self._and()
        while self.at_punct("||"):
            self.next()
            right = self._and()
            left = Term(op="or", args=[left, right])
        return left

    def _and(self) -> Term:
        left = self._cmp()
        while self.at_punct("&&"):
            self.next()
            right = self._cmp()
            left = Term(op="and", args=[left, right])
        return left

    def _cmp(self) -> Term:
        left = self._add()
        tok = self.peek()
        if (
            tok is not None
            and tok.kind == "punct"
            and tok.value in ("==", "!=", "<", "<=", ">", ">=")
        ):
            self.next()
            right = self._add()
            op = {"==": "eq", "!=": "neq", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}[tok.value]
            return Term(op=op, args=[left, right])
        return left

    def _add(self) -> Term:
        left = self._mul()
        while self.at_punct("+", "-"):
            op = self.next().value
            right = self._mul()
            left = Term(op="add" if op == "+" else "sub", args=[left, right])
        return left

    def _mul(self) -> Term:
        left = self._unary()
        while self.at_punct("*", "/", "%"):
            op = self.next().value
            right = self._unary()
            node = {"*": "mul", "/": "intdiv", "%": "mod"}[op]
            left = Term(op=node, args=[left, right])
        return left

    def _unary(self) -> Term:
        if self.at_punct("!"):
            self.next()
            return Term(op="not", args=[self._unary()])
        if self.at_punct("-"):
            self.next()
            inner = self._unary()
            if inner.op == "const" and isinstance(inner.args[0], int):
                return Term(op="const", args=[-inner.args[0]])
            return Term(op="neg", args=[inner])
        return self._primary()

    def _primary(self) -> Term:
        tok = self.next()
        if tok.kind == "number":
            try:
                value = _strip_int_suffix(tok.value)
            except ValueError as e:
                raise VerusImportError(
                    "semantic-mismatch", str(e), tok.line_no, tok.line_text
                ) from None
            return Term(op="const", args=[value])
        if tok.kind == "ident":
            if tok.value in ("forall", "exists"):
                raise self.fail_out_of_subset(
                    tok, f"quantifier {tok.value!r} is outside the import subset"
                )
            if tok.value in ("old", "call", "return", "true", "false"):
                if tok.value in ("true", "false"):
                    return Term(op="const", args=[tok.value == "true"])
                raise self.fail_out_of_subset(
                    tok, f"{tok.value!r}(...) is outside the import subset"
                )
            nxt = self.peek()
            if nxt is not None and nxt.kind == "punct" and nxt.value == "(":
                raise self.fail_out_of_subset(
                    tok, f"function call {tok.value!r}(...) is outside the import subset"
                )
            if nxt is not None and nxt.kind == "punct" and nxt.value == "::":
                raise self.fail_out_of_subset(
                    tok,
                    f"path expression {tok.value!r}:: is outside the import subset",
                )
            return Term(op="var", args=[tok.value])
        if tok.kind == "punct" and tok.value == "(":
            inner = self.parse()
            self.expect(")")
            return inner
        raise self.fail_out_of_subset(tok, f"unexpected token {tok.value!r}")


# --- structure parser (the verus! block subset) ---------------------------------------


def _find_verus_blocks(source: str) -> list[tuple[int, int]]:
    """`verus! {` ... matching-close spans (start after the brace)."""
    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        j = source.find("verus!", i)
        if j < 0:
            break
        k = source.find("{", j)
        if k < 0:
            break
        depth = 1
        m = k + 1
        while m < len(source) and depth:
            if source[m] == "{":
                depth += 1
            elif source[m] == "}":
                depth -= 1
            m += 1
        if depth:
            line_no, line_text = _line_of(source, j)
            raise VerusImportError("parse", "unterminated verus! block", line_no, line_text)
        spans.append((k + 1, m - 1))
        i = m
    return spans


def _parse_params(parser: _ExprParser) -> dict[str, str]:
    """`(x: i32, y: bool)` -> {name: sort}; anything else fails loud."""
    sorts: dict[str, str] = {}
    parser.expect("(")
    if parser.at_punct(")"):
        parser.next()
        return sorts
    while True:
        name = parser.next()
        if name.kind != "ident":
            raise VerusImportError(
                "parse",
                f"expected a parameter name, got {name.value!r}",
                name.line_no,
                name.line_text,
            )
        parser.expect(":")
        ty = parser.next()
        if ty.kind != "ident" or ty.value not in _IN_SUBSET_TYPES:
            raise VerusImportError(
                "semantic-mismatch",
                f"parameter type {ty.value!r} is outside the import subset "
                f"(scalar {sorted(set(_IN_SUBSET_TYPES))} only)",
                ty.line_no,
                ty.line_text,
            )
        sorts[name.value] = _IN_SUBSET_TYPES[ty.value]
        if parser.at_punct(","):
            parser.next()
            if parser.at_punct(")"):
                parser.next()
                return sorts
            continue
        parser.expect(")")
        return sorts


def _parse_spec_clause(parser: _ExprParser, keyword: str) -> list[Term]:
    """`requires e, e,` / `ensures e, e,` (comma form); the braced form and
    `recommends`/`decreases` fail loud. Clauses end at the next keyword or
    the body brace."""
    clauses: list[Term] = []
    while True:
        clauses.append(parser.parse())
        if parser.at_punct(","):
            parser.next()
        else:
            break
        tok = parser.peek()
        if (
            tok is not None
            and tok.kind == "ident"
            and tok.value in ("requires", "ensures", "recommends", "decreases")
        ):
            break
        if parser.at_punct("{"):
            break
    _ = keyword
    return clauses


def _parse_body(parser: _ExprParser, sorts: dict[str, str]) -> list[Term]:
    """Straight-line body: `let x = e;` / `x = e;` / `assert(e);` - each
    assert is an obligation; lets/assignments forward-propagate into the
    sequents (applied INCREMENTALLY at each statement, so shadowing and
    statement order are honored exactly). Loops, `if`, `return`, and
    anything else fail loud."""
    goals: list[Term] = []
    bindings: dict[str, Term] = {}
    parser.expect("{")
    while not parser.at_punct("}"):
        tok = parser.peek()
        if tok is None:
            raise VerusImportError("parse", "unexpected end of procedure body", 0, "")
        if tok.kind == "punct" and tok.value == ";":
            parser.next()
            continue
        if tok.kind == "ident" and tok.value in (
            "while",
            "for",
            "loop",
            "if",
            "else",
            "return",
            "match",
        ):
            raise VerusImportError(
                "parse",
                f"statement {tok.value!r} is outside the import subset (straight-line bodies only)",
                tok.line_no,
                tok.line_text,
            )
        if tok.kind == "ident" and tok.value == "let":
            parser.next()
            name = parser.next()
            if name.kind != "ident":
                raise VerusImportError(
                    "parse",
                    f"expected a binding name, got {name.value!r}",
                    name.line_no,
                    name.line_text,
                )
            parser.expect("=")
            expr = parser.parse()
            parser.expect(";")
            bound = _substitute(expr, bindings)
            sorts[name.value] = _expr_sort(bound, sorts)
            bindings[name.value] = bound
            continue
        if tok.kind == "ident" and tok.value == "assert":
            parser.next()
            parser.expect("(")
            expr = parser.parse()
            parser.expect(")")
            parser.expect(";")
            goals.append(_substitute(expr, bindings))
            continue
        # plain assignment `x = e;`
        name = parser.next()
        if name.kind != "ident":
            raise VerusImportError(
                "parse",
                f"expected a statement, got {name.value!r}",
                name.line_no,
                name.line_text,
            )
        parser.expect("=")
        expr = parser.parse()
        parser.expect(";")
        bound = _substitute(expr, bindings)
        sorts[name.value] = _expr_sort(bound, sorts)
        bindings[name.value] = bound
    parser.expect("}")
    return goals


def _expr_sort(expr: Term, sorts: dict[str, str]) -> str:
    names = term_vars(expr)
    for n in sorted(names):
        if n in sorts:
            return sorts[n]
    return "int"


def _substitute(expr: Term, bindings: dict[str, Term]) -> Term:
    """Apply the current let-bindings to a term by rebuilding var nodes
    (forward propagation; shadowing is honored by construction)."""
    if not bindings:
        return expr
    if expr.op == "var" and expr.args and isinstance(expr.args[0], str):
        bound = bindings.get(expr.args[0])
        if bound is not None:
            return bound
        return expr
    from ...artifacts.terms import TermArg

    rebuilt: list[TermArg] = []
    for a in expr.args:
        if isinstance(a, Term):
            rebuilt.append(_substitute(a, bindings))
        else:
            rebuilt.append(a)
    return Term(op=expr.op, args=rebuilt)


def import_verus(source: str, filename: str = "input.rs") -> ImportResult:
    """Import a Verus .rs artifact; returns the common-core import shapes +
    I7 parse/semantic-mismatch diagnostics (fail loud)."""
    result = ImportResult(filename=filename)
    try:
        blocks = _find_verus_blocks(source)
        if not blocks:
            line_no, line_text = _line_of(source, 0)
            raise VerusImportError("parse", "no verus! block found", line_no, line_text)
        for start, end in blocks:
            _import_block(source, start, end, filename, result)
    except VerusImportError as e:
        result.diagnostics.append(
            Diagnostic(
                obligation_ref=None,
                kind=e.kind,  # type: ignore[arg-type]
                loc=Loc(file=filename, line=e.line_no or None),
                native_message=f"{e.message}\n{e.line_text.strip()}".strip(),
            )
        )
    return result


def _import_block(source: str, start: int, end: int, filename: str, result: ImportResult) -> None:
    tokens = _tokenize(source, start, end)
    parser = _ExprParser(tokens, 0)
    while parser.peek() is not None:
        tok = parser.next()
        if tok.kind == "punct" and tok.value == ";":
            continue
        if tok.kind == "ident" and tok.value in ("pub", "open"):
            raise VerusImportError(
                "semantic-mismatch",
                f"item modifier {tok.value!r} is outside the import subset",
                tok.line_no,
                tok.line_text,
            )
        if tok.kind == "ident" and tok.value in (
            "spec",
            "proof",
            "uninterp",
            "enum",
            "struct",
            "impl",
            "use",
            "global",
            "axiom",
        ):
            raise VerusImportError(
                "semantic-mismatch",
                f"top-level {tok.value!r} declarations are outside the import subset",
                tok.line_no,
                tok.line_text,
            )
        if not (tok.kind == "ident" and tok.value == "fn"):
            raise VerusImportError(
                "parse", f"expected a fn declaration, got {tok.value!r}", tok.line_no, tok.line_text
            )
        name = parser.next()
        if name.kind != "ident":
            raise VerusImportError(
                "parse", f"expected a fn name, got {name.value!r}", name.line_no, name.line_text
            )
        sorts = _parse_params(parser)
        _expect_unit_return(parser)
        requires: list[Term] = []
        ensures: list[Term] = []
        while True:
            nxt = parser.peek()
            if nxt is not None and nxt.kind == "ident" and nxt.value in ("requires", "ensures"):
                keyword = parser.next()
                clauses = _parse_spec_clause(parser, keyword.value)
                if keyword.value == "requires":
                    requires.extend(clauses)
                else:
                    ensures.extend(clauses)
                continue
            if (
                nxt is not None
                and nxt.kind == "ident"
                and nxt.value
                in ("recommends", "decreases", "invariant_except", "invariant", "asserts", "opens")
            ):
                raise VerusImportError(
                    "semantic-mismatch",
                    f"{nxt.value!r} clauses are outside the import subset",
                    nxt.line_no,
                    nxt.line_text,
                )
            break
        goals = _parse_body(parser, sorts)
        if not ensures and not goals:
            raise VerusImportError(
                "semantic-mismatch",
                "fn without ensures or asserts yields no obligations (outside the import subset)",
                name.line_no,
                name.line_text,
            )
        result.procedures[name.value] = _lower_procedure(
            name.value, filename, source, sorts, requires, ensures + goals
        )


def _expect_unit_return(parser: _ExprParser) -> None:
    nxt = parser.peek()
    if nxt is not None and nxt.kind == "punct" and nxt.value == "->":
        arrow = parser.next()
        raise VerusImportError(
            "parse",
            "non-unit return types are outside the import subset",
            arrow.line_no,
            arrow.line_text,
        )


def _lower_procedure(
    name: str,
    filename: str,
    source: str,
    sorts: dict[str, str],
    requires: list[Term],
    goals: list[Term],
) -> ProcedureImport:
    program = Program(
        language="verus-rust",
        source_ref=filename,
        symbol=name,
        fragment=source.strip(),
        semantics_model=VERUS_SUBSET_V1.model_id,
        notes=(
            "imported by uvil.adapters.verus (vendor-TCB caveat: Verus "
            "generates and solves its own VCs; UVIL consumes its artifacts "
            "as a frontend and re-dispatches all verdicts through its own "
            "backends). Harness abstraction: sequents are unbounded-Int - "
            "Verus's bounded machine semantics are intentionally not modeled, "
            "which is why the native verdict never upgrades an obligation."
        ),
    )
    sort_theory = {"int": "uvil.core.int@1", "bool": "uvil.core.bool@1"}
    theories: list[str] = []
    for sort in sorts.values():
        theory = sort_theory[sort]
        if theory not in theories:
            theories.append(theory)
    if not theories:
        theories = ["uvil.core.int@1"]

    spec = Specification(
        profile=VERUS_TARGET_PROFILE,
        theories=theories,
        semantics_model=VERUS_SUBSET_V1.model_id,
        subject=name,
        contracts=Contracts(requires=requires, ensures=[]),
    )
    spec_aid = artifact_id(spec)
    program_aid = artifact_id(program)

    context = list(requires)
    obligations: list[Obligation] = []
    for goal in goals:
        names = sorted(term_vars(goal) | {v for c in context for v in term_vars(c)})
        obligations.append(
            Obligation(
                spec_ref=spec_aid,
                program_ref=program_aid,
                semantics_model=VERUS_SUBSET_V1.model_id,
                sequent=Sequent(
                    context=list(context),
                    goal=goal,
                    var_sorts={
                        v: {"int": "Int", "bool": "Bool"}[sorts.get(v, "int")] for v in names
                    },
                ),
                theories=theories,
                target_profile=VERUS_TARGET_PROFILE,
                status="open",
                cost_budget=CostBudget(solver_ms=DEFAULT_SOLVER_MS),
                origin_backend="verus-import",
            )
        )
    return ProcedureImport(name=name, program=program, spec=spec, obligations=obligations)


# --- optional native Verus run probe (UVIL_VERUS, skip-if-absent) ------------------------


VERUS_ENV_VAR = "UVIL_VERUS"


def find_verus() -> str | None:
    """The pinned Verus binary, or None when absent (skip-if-absent)."""
    override = os.environ.get(VERUS_ENV_VAR)
    if override:
        return override if Path(override).exists() else None
    found = shutil.which("verus")
    return found


@dataclass
class VerusRunResult:
    filename: str
    exit_code: int
    raw_output: str


def verus_verify(executable: str, file: Path, timeout_s: float = 300) -> VerusRunResult:
    """Run the pinned native Verus on one artifact; the output is consumed
    VERBATIM only (discovery-first discipline - the per-goal `✅/error` lines
    and the `verification results::` summary are recorded, never interpreted
    into UVIL verdicts). Decoded as UTF-8 with replacement (the strata
    precedent: platform-codepage decoding loses the capture entirely)."""
    proc = subprocess.run(
        [executable, str(file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout_s,
    )
    return VerusRunResult(
        filename=file.name,
        exit_code=proc.returncode,
        raw_output=(proc.stdout + proc.stderr).strip(),
    )
