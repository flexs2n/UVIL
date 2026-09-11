"""Strata import adapter: Strata dialect artifacts (.st) -> I2/I3/I4.

**Vendor-TCB caveat (recorded in every artifact this adapter produces):**
Strata (github.com/strata-org/Strata) unifies dialects toward a vendor Lean
core; UVIL consumes its artifacts as a FRONTEND, not a neutral peer - Strata's
VC generation is not UVIL's TCB. Imported obligations are ordinary I4s: any
guarantee they carry must come from UVIL's own backends (`uvil check`
re-dispatches the shared-subset VCs through the pinned z3/cvc5 - solver-verdict
G1), never from the vendor pipeline. Vendor verdicts, when the pinned
Strata-CLI is available (`UVIL_STRATA`), are recorded as I5 opaque payloads
(`format="strata-verifier-result"`, `checker.independent=False`) - provenance
preserved, no fabricated guarantee.

Pinned by repo commit hash (ADR 0002 discipline): PINNED_STRATA_COMMIT +
recorded toolchain. The import path is discovery-first against the REAL
artifacts of the pinned checkout (copied verbatim into corpora/strata/
upstream/ with provenance in the manifest): `program Core;` procedures with
scalar int/bool parameters, `spec { requires/ensures }`, straight-line bodies
(`var`, `:=`, `assert [label]: (expr)`, `return`), and the operator surface
the pinned artifacts exercise (prefix `int.add/sub/mul/div/mod/neg/lt/le/gt/ge`
calls, infix `==`/`&&`/`||`). Anything else fails loud: dialect/CFG/while/call
shapes surface as I7 `parse` with the verbatim line; bv/Map-typed procedures
surface as I7 `semantic-mismatch` with the verbatim fragment (the shared
theories carry no bit-vector/map semantics).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ...artifacts import Obligation, Program, Specification, artifact_id
from ...artifacts.diagnostic import Diagnostic, Loc
from ...artifacts.obligation import CostBudget, Sequent
from ...artifacts.proof import BackendDescriptor, Checker, Proof, ProofPayload
from ...artifacts.spec import Contracts
from ...artifacts.terms import Term, term_vars
from ...semmodels.registry import STRATA_CORE_V1
from ..boogie.lower import ImportResult, ProcedureImport  # the common core shapes

STRATA_TARGET_PROFILE = "uvil.strata-core@1"
DEFAULT_SOLVER_MS = 2000

STRATA_REPO = "https://github.com/strata-org/Strata"
PINNED_STRATA_COMMIT = "90f211c49f9dcee6e291a9a0b667b382f7c25719"
PINNED_STRATA_TOOLCHAIN = "leanprover/lean4:v4.29.1"
STRATA_ENV_VAR = "UVIL_STRATA"
VENDOR_PAYLOAD_FORMAT = "strata-verifier-result"

_IN_SUBSET_TYPES = {"int", "bool"}


class StrataImportError(ValueError):
    """Out-of-subset Strata artifact (fail loud): message + verbatim line."""

    def __init__(self, kind: str, message: str, line_no: int, line_text: str) -> None:
        super().__init__(f"{message}\n{line_text.strip()}")
        self.kind = kind
        self.message = message
        self.line_no = line_no
        self.line_text = line_text


# --- tokenizer ------------------------------------------------------------------------


@dataclass(frozen=True)
class Tok:
    kind: str  # "ident" | "int" | "punct" | "label"
    value: str
    line_no: int
    line_text: str


_PUNCT = [
    ":=",
    "==",
    "!=",
    "<=",
    ">=",
    "&&",
    "||",
    "=>",
    "(",
    ")",
    "{",
    "}",
    ";",
    ":",
    ",",
    "[",
    "]",
    "<",
    ">",
    "=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "!",
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
        if ch == "[":
            j = source.find("]", i)
            if j < 0:
                line_no, line_text = _line_of(source, i)
                raise StrataImportError("parse", "unterminated label", line_no, line_text)
            line_no, line_text = _line_of(source, i)
            tokens.append(Tok("label", source[i + 1 : j].strip(), line_no, line_text))
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
            while j < n and (source[j].isalnum() or source[j] == "_" or source[j] == "."):
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
            raise StrataImportError("parse", f"unexpected character {ch!r}", line_no, line_text)
    return tokens


# --- expression parser ------------------------------------------------------------------


class _ExprParser:
    """Expressions over the pinned artifact surface: prefix `int.*` calls and
    infix `== != < <= > >= && || !`."""

    def __init__(self, tokens: list[Tok], pos: int) -> None:
        self.toks = tokens
        self.pos = pos

    def peek(self) -> Tok | None:
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def next(self) -> Tok:
        tok = self.peek()
        if tok is None:
            raise StrataImportError("parse", "unexpected end of input", 0, "")
        self.pos += 1
        return tok

    def expect(self, value: str) -> Tok:
        tok = self.next()
        if tok.kind != "punct" or tok.value != value:
            raise StrataImportError(
                "parse", f"expected {value!r}, got {tok.value!r}", tok.line_no, tok.line_text
            )
        return tok

    def at_punct(self, *values: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "punct" and tok.value in values

    def parse(self) -> Term:
        left = self.logic_or()
        return left

    def logic_or(self) -> Term:
        left = self.logic_and()
        while self.at_punct("||"):
            self.next()
            left = Term(op="or", args=[left, self.logic_and()])
        return left

    def logic_and(self) -> Term:
        left = self.logic_not()
        while self.at_punct("&&"):
            self.next()
            left = Term(op="and", args=[left, self.logic_not()])
        return left

    def logic_not(self) -> Term:
        if self.at_punct("!"):
            self.next()
            return Term(op="not", args=[self.logic_not()])
        return self.comparison()

    def comparison(self) -> Term:
        left = self.primary()
        tok = self.peek()
        if (
            tok is not None
            and tok.kind == "punct"
            and tok.value in ("==", "!=", "<", "<=", ">", ">=")
        ):
            self.next()
            right = self.primary()
            op = {"==": "eq", "!=": "neq", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}[tok.value]
            return Term(op=op, args=[left, right])
        return left

    def primary(self) -> Term:
        tok = self.next()
        if tok.kind == "int":
            return Term(op="const", args=[int(tok.value)])
        if tok.kind == "ident":
            name = tok.value
            if name == "true":
                return Term(op="const", args=[True])
            if name == "false":
                return Term(op="const", args=[False])
            if self.at_punct("("):
                call_tok = tok
                self.next()  # consume '('
                args: list[Term] = []
                if not self.at_punct(")"):
                    args.append(self.logic_or())
                    while self.at_punct(","):
                        self.next()
                        args.append(self.logic_or())
                self.expect(")")
                return _call_term(call_tok, name, args)
            return Term(op="var", args=[name])
        raise StrataImportError(
            "parse", f"unexpected token {tok.value!r} in expression", tok.line_no, tok.line_text
        )


def _call_term(tok: Tok, name: str, args: list[Term]) -> Term:
    """Map the pinned operator surface onto core terms; unknown operators are
    out of the shared theories (semantic-mismatch, verbatim fragment)."""
    int_ops = {
        "int.add": "add",
        "int.sub": "sub",
        "int.mul": "mul",
        "int.div": "intdiv",
        "int.mod": "mod",
        "int.neg": "neg",
        "int.lt": "lt",
        "int.le": "le",
        "int.gt": "gt",
        "int.ge": "ge",
    }
    if name in int_ops:
        op = int_ops[name]
        if op == "neg":
            if len(args) != 1:
                raise StrataImportError(
                    "semantic-mismatch", f"{name} expects one argument", tok.line_no, tok.line_text
                )
            return Term(op="neg", args=list(args))
        return Term(op=op, args=list(args))
    raise StrataImportError(
        "semantic-mismatch",
        f"operator {name!r} is outside the shared theories (no core rendering)",
        tok.line_no,
        tok.line_text,
    )


# --- procedure parser -------------------------------------------------------------------


def _parse_type(tok: Tok) -> str:
    """Scalar int/bool are in the shared subset; anything else fails with the
    verbatim type text (semantic-mismatch). Qualified types (bv W32, Map int
    int, seq) land here too."""
    if tok.value in _IN_SUBSET_TYPES:
        return tok.value
    raise StrataImportError(
        "semantic-mismatch",
        f"type {tok.value!r} has no shared-theory semantics",
        tok.line_no,
        tok.line_text,
    )


def _parse_params(parser: _ExprParser) -> tuple[dict[str, str], list[str]]:
    """`( [in|out|inout] name : type , ... )` -> (name -> sort, names)."""
    sorts: dict[str, str] = {}
    order: list[str] = []
    parser.expect("(")
    if not parser.at_punct(")"):
        while True:
            tok = parser.peek()
            if tok is not None and tok.kind == "ident" and tok.value in ("in", "out", "inout"):
                parser.next()
            name_tok = parser.next()
            if name_tok.kind != "ident":
                raise StrataImportError(
                    "parse",
                    f"expected a parameter name, got {name_tok.value!r}",
                    name_tok.line_no,
                    name_tok.line_text,
                )
            parser.expect(":")
            type_tok = parser.next()
            sort = _parse_type(type_tok)
            sorts[name_tok.value] = sort
            order.append(name_tok.value)
            if not parser.at_punct(","):
                break
            parser.next()
    parser.expect(")")
    return sorts, order


def _parse_spec(parser: _ExprParser) -> tuple[list[Term], list[Term]]:
    """`spec { requires (e); ensures (e); }` -> (requires, ensures)."""
    requires: list[Term] = []
    ensures: list[Term] = []
    tok = parser.next()
    if not (tok.kind == "ident" and tok.value == "spec"):
        raise StrataImportError(
            "parse", f"expected 'spec', got {tok.value!r}", tok.line_no, tok.line_text
        )
    parser.expect("{")
    while not parser.at_punct("}"):
        tok = parser.next()
        if not (tok.kind == "ident" and tok.value in ("requires", "ensures")):
            raise StrataImportError(
                "parse",
                f"only requires/ensures are supported in spec, got {tok.value!r}",
                tok.line_no,
                tok.line_text,
            )
        parser.expect("(")
        term = parser.parse()
        parser.expect(")")
        parser.expect(";")
        (requires if tok.value == "requires" else ensures).append(term)
    parser.expect("}")
    return requires, ensures


def _parse_body(
    parser: _ExprParser, sorts: dict[str, str]
) -> tuple[list[Term], list[Term], list[Term]]:
    """Straight-line body -> (assumption-free context, assertion goals,
    ensures-like contracts). Assignments update the imported environment for
    later statements (no weakest-precondition computation - the documented M1
    discipline, recorded on the Program artifact)."""
    goals: list[Term] = []
    env: dict[str, Term | None] = {name: Term(op="var", args=[name]) for name in sorts}
    while not parser.at_punct("}"):
        tok = parser.next()
        if tok.kind == "ident" and tok.value == "var":
            name_tok = parser.next()
            if name_tok.kind != "ident":
                raise StrataImportError(
                    "parse",
                    f"expected a name after 'var', got {name_tok.value!r}",
                    name_tok.line_no,
                    name_tok.line_text,
                )
            parser.expect(":")
            type_tok = parser.next()
            _parse_type(type_tok)
            parser.expect(";")
            env.setdefault(name_tok.value, Term(op="var", args=[name_tok.value]))
        elif tok.kind == "ident" and tok.value == "return":
            parser.expect(";")
        elif tok.kind == "ident" and tok.value == "assert":
            label = parser.next()
            if label.kind != "label":
                raise StrataImportError(
                    "parse",
                    f"expected an [assertion label], got {label.value!r}",
                    label.line_no,
                    label.line_text,
                )
            parser.expect(":")
            parser.expect("(")
            term = parser.parse()
            parser.expect(")")
            parser.expect(";")
            goals.append(term)
        elif tok.kind == "ident" and tok.value in ("while", "if", "call", "goto"):
            raise StrataImportError(
                "parse",
                f"statement {tok.value!r} is outside the import subset (straight-line bodies only)",
                tok.line_no,
                tok.line_text,
            )
        elif tok.kind == "ident":
            name = tok.value
            parser.expect(":=")
            rhs = parser.parse()
            parser.expect(";")
            env[name] = rhs
        else:
            raise StrataImportError(
                "parse",
                f"statement {tok.value!r} is outside the import subset",
                tok.line_no,
                tok.line_text,
            )
    parser.expect("}")
    # substitute the environment into goals (forward assignment propagation)
    from ..boogie.lower import substitute

    return [], [substitute(g, {k: v for k, v in env.items() if v is not None}) for g in goals], []


def import_strata(source: str, filename: str = "input.st") -> ImportResult:
    """Import a Strata `program Core` artifact; returns the common-core
    import shapes + I7 parse/semantic-mismatch diagnostics (fail loud)."""
    result = ImportResult(filename=filename)
    try:
        tokens = _tokenize(source)
        parser = _ExprParser(tokens, 0)
        header = parser.next()
        if not (header.kind == "ident" and header.value == "program"):
            raise StrataImportError(
                "parse",
                "expected a `program <Dialect>;` header",
                header.line_no,
                header.line_text,
            )
        dialect = parser.next()
        if not (dialect.kind == "ident" and dialect.value == "Core"):
            raise StrataImportError(
                "parse",
                f"dialect {dialect.value!r} is outside the import subset "
                "(only `program Core` artifacts are supported)",
                dialect.line_no,
                dialect.line_text,
            )
        parser.expect(";")

        while parser.peek() is not None:
            tok = parser.next()
            if not (tok.kind == "ident" and tok.value == "procedure"):
                if tok.kind == "ident" and tok.value in ("global", "axiom", "constant", "function"):
                    raise StrataImportError(
                        "parse",
                        f"top-level {tok.value!r} declarations are outside the import subset",
                        tok.line_no,
                        tok.line_text,
                    )
                raise StrataImportError(
                    "parse",
                    f"expected a procedure declaration, got {tok.value!r}",
                    tok.line_no,
                    tok.line_text,
                )
            name_tok = parser.next()
            if name_tok.kind != "ident":
                raise StrataImportError(
                    "parse",
                    f"expected a procedure name, got {name_tok.value!r}",
                    name_tok.line_no,
                    name_tok.line_text,
                )
            sorts, _order = _parse_params(parser)
            requires: list[Term] = []
            ensures: list[Term] = []
            nxt = parser.peek()
            if nxt is not None and nxt.kind == "ident" and nxt.value == "spec":
                requires, ensures = _parse_spec(parser)
            nxt = parser.peek()
            if nxt is None:
                raise StrataImportError(
                    "parse",
                    "unexpected end of input in procedure body",
                    name_tok.line_no,
                    name_tok.line_text,
                )
            if nxt.kind == "ident" and nxt.value == "cfg":
                raise StrataImportError(
                    "parse",
                    "CFG procedure bodies are outside the import subset",
                    nxt.line_no,
                    nxt.line_text,
                )
            if not (nxt.kind == "punct" and nxt.value == "{"):
                raise StrataImportError(
                    "parse",
                    f"expected '{{' to open the body, got {nxt.value!r}",
                    nxt.line_no,
                    nxt.line_text,
                )
            parser.next()
            _assumptions, goals, _contracts = _parse_body(parser, sorts)
            parser.expect(";")

            result.procedures[name_tok.value] = _lower_procedure(
                name_tok.value, source, filename, sorts, requires, ensures, goals
            )
    except StrataImportError as e:
        result.diagnostics.append(
            Diagnostic(
                obligation_ref=None,
                kind=e.kind,  # type: ignore[arg-type]
                loc=Loc(file=filename, line=e.line_no or None),
                native_message=f"{e.message}\n{e.line_text.strip()}".strip(),
            )
        )
    return result


def _lower_procedure(
    name: str,
    source: str,
    filename: str,
    sorts: dict[str, str],
    requires: list[Term],
    ensures: list[Term],
    goals: list[Term],
) -> ProcedureImport:
    program = Program(
        language="strata-core",
        source_ref=filename,
        symbol=name,
        fragment=source.strip(),
        semantics_model=STRATA_CORE_V1.model_id,
        notes=(
            "imported by uvil.adapters.strata (vendor-TCB caveat: Strata "
            "unifies toward a vendor Lean core; UVIL consumes its artifacts "
            "as a frontend and re-dispatches all verdicts through its own "
            "backends). M1 no-WP discipline: obligations come from asserts; "
            "assignments are forward-propagated into the sequents."
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
        profile=STRATA_TARGET_PROFILE,
        theories=theories,
        semantics_model=STRATA_CORE_V1.model_id,
        subject=name,
        contracts=Contracts(requires=requires, ensures=ensures),
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
                semantics_model=STRATA_CORE_V1.model_id,
                sequent=Sequent(
                    context=list(context),
                    goal=goal,
                    var_sorts={
                        v: {"int": "Int", "bool": "Bool"}[sorts.get(v, "int")] for v in names
                    },
                ),
                theories=theories,
                target_profile=STRATA_TARGET_PROFILE,
                status="open",
                cost_budget=CostBudget(solver_ms=DEFAULT_SOLVER_MS),
                origin_backend="strata-import",
            )
        )
    return ProcedureImport(name=name, program=program, spec=spec, obligations=obligations)


# --- optional vendor verify probe (UVIL_STRATA, skip-if-absent) --------------------------


@dataclass
class StrataVerifyResult:
    filename: str
    exit_code: int
    raw_output: str


def find_strata() -> str | None:
    """The pinned Strata-CLI binary, or None when absent (skip-if-absent)."""
    return os.environ.get(STRATA_ENV_VAR)


def strata_verify(executable: str, file: Path, timeout_s: float = 120) -> StrataVerifyResult:
    """Run `strata verify` on one artifact; the output is consumed VERBATIM
    only - never screen-scraped into verdicts (discovery-first discipline).
    Decoded as UTF-8 with replacement (live discovery, 2026-09-11: the pinned
    CLI emits UTF-8 symbols on Windows consoles that default to the ANSI
    codepage; strict cp1252 decoding raises inside the reader thread and
    loses the captured output entirely)."""
    proc = subprocess.run(
        [executable, "verify", str(file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout_s,
    )
    return StrataVerifyResult(
        filename=file.name,
        exit_code=proc.returncode,
        raw_output=(proc.stdout + proc.stderr).strip(),
    )


def vendor_result_proof(obl: Obligation, verify_result: StrataVerifyResult) -> Proof:
    """The vendor verdict as an opaque I5 payload: provenance preserved,
    `independent=False` (the vendor pipeline is not UVIL's TCB and this is
    never a G-carrying kernel proof)."""
    return Proof(
        obligation_ref=artifact_id(obl),
        backend=BackendDescriptor(
            name="strata-cli",
            version=f"commit {PINNED_STRATA_COMMIT[:12]}",
        ),
        payload=ProofPayload(
            format=VENDOR_PAYLOAD_FORMAT,
            inline=verify_result.raw_output,
            metadata={"exit_code": verify_result.exit_code, "file": verify_result.filename},
        ),
        checker=Checker(
            entry="strata verify",
            independent=False,
            version=f"commit {PINNED_STRATA_COMMIT[:12]}",
        ),
    )
