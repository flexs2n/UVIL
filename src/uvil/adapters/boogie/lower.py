"""Lowering: parse results -> I2/I3/I4 artifacts (+ I7 diagnostics, fail-loud).

One I3 Program and one I2 Specification per procedure; the I4 Obligations are
the WP verification conditions computed by `vcgen.wp_procedure` (sound weakest
preconditions over the accepted subset, recorded as `origin_backend="boogie-wp"`,
ADR 0008). Anything outside the subset surfaces as an I7 `parse` diagnostic
preserving the verbatim source line - out-of-subset input is never silently
skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...artifacts import Obligation, Program, Specification, artifact_id
from ...artifacts.diagnostic import Diagnostic, Loc
from ...artifacts.obligation import CostBudget, Sequent
from ...artifacts.spec import Contracts
from ...artifacts.terms import Term, TermArg, term_vars  # term_vars re-exported for callers
from ...semmodels.registry import WHY3_MEMORY_V1
from .parser import (
    BOOGIE_TARGET_PROFILE,
    BoogieModule,
    BoogieParseError,
    FunctionDecl,
    ProcedureDecl,
    VarStmt,
    parse_module_tolerant,
)
from .vcgen import substitute, wp_procedure

__all__ = ["ImportResult", "ProcedureImport", "import_module", "substitute", "term_vars"]

DEFAULT_SOLVER_MS = 2000

_SORT_THEORY = {
    "int": "uvil.core.int@1",
    "bool": "uvil.core.bool@1",
    "real": "uvil.core.real@1",
    "array": "uvil.core.array@1",
    "seq": "uvil.core.seq@1",
}

_SORT_SMT = {
    "int": "Int",
    "bool": "Bool",
    "real": "Real",
    "array": "(Array Int Int)",
    "seq": "(Seq Int)",
}


@dataclass
class ProcedureImport:
    name: str
    program: Program
    spec: Specification
    obligations: list[Obligation]


@dataclass
class ImportResult:
    filename: str
    procedures: dict[str, ProcedureImport] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    @property
    def obligations(self) -> list[Obligation]:
        return [o for p in self.procedures.values() for o in p.obligations]


def _parse_error_diagnostic(e: BoogieParseError, filename: str) -> Diagnostic:
    return Diagnostic(
        obligation_ref=None,
        kind="parse",
        loc=Loc(file=filename, line=e.line_no or None),
        native_message=f"{e.message}\n{e.line_text.strip()}".strip(),
    )


def import_module(source: str, filename: str = "input.bpl") -> ImportResult:
    """Import Boogie text; returns artifacts per procedure + I7 parse diagnostics."""
    outcome = parse_module_tolerant(source, name=filename)
    result = ImportResult(filename=filename)
    result.diagnostics.extend(_parse_error_diagnostic(e, filename) for e in outcome.errors)
    module = outcome.module
    if module is None:
        return result
    for proc in module.procedures:
        try:
            result.procedures[proc.name] = _lower_procedure(module, proc, source, filename)
        except BoogieParseError as e:
            result.diagnostics.append(_parse_error_diagnostic(e, filename))
    return result


def _lower_procedure(
    module: BoogieModule, proc: ProcedureDecl, source: str, filename: str
) -> ProcedureImport:
    fn_bodies: dict[str, FunctionDecl] = {f.name: f for f in module.functions if f.body is not None}
    fn_all = {f.name for f in module.functions}

    def resolve_calls(term: Term) -> Term:
        if term.op == "call" and term.args and isinstance(term.args[0], str):
            fname = term.args[0]
            resolved = [resolve_calls(a) if isinstance(a, Term) else a for a in term.args[1:]]
            if fname in fn_bodies:
                fn = fn_bodies[fname]
                if len(resolved) != len(fn.params):
                    raise BoogieParseError(
                        f"function {fname!r} called with {len(resolved)} argument(s), "
                        f"declared with {len(fn.params)}",
                        0,
                        "",
                    )
                mapping = {
                    p.name: a
                    for p, a in zip(fn.params, resolved, strict=True)
                    if isinstance(a, Term)
                }
                return substitute(fn.body, mapping) if fn.body is not None else term
            if fname in fn_all:
                raise BoogieParseError(
                    f"uninterpreted function {fname!r} has no definition body; "
                    "calling definition-less functions is outside the accepted M1 subset",
                    0,
                    "",
                )
            raise BoogieParseError(f"unknown function {fname!r} in expression", 0, "")
        new_args: list[TermArg] = []
        for a in term.args:
            new_args.append(resolve_calls(a) if isinstance(a, Term) else a)
        return Term(op=term.op, args=new_args)

    # Name -> Boogie sort, for seq/array disambiguation (already resolved at parse
    # time) and for the sequent's var_sorts map consumed by the SMT encoder.
    sorts: dict[str, str] = {v.name: v.type.sort for v in module.vars}
    for p in proc.params + proc.returns:
        sorts[p.name] = p.type.sort
    for stmt in proc.body:
        if isinstance(stmt, VarStmt):
            sorts[stmt.name] = stmt.type.sort

    requires = [resolve_calls(r) for r in proc.requires]
    ensures = [resolve_calls(e) for e in proc.ensures]

    # entry context: axioms, const definitions, preconditions (the WP walk
    # folds assumes/loop frames into per-obligation contexts from here)
    base_context: list[Term] = []
    for ax in module.axioms:
        base_context.append(resolve_calls(ax.term))
    for c in module.consts:
        if c.definition is not None:
            base_context.append(
                resolve_calls(Term(op="eq", args=[Term(op="var", args=[c.name]), c.definition]))
            )
    base_context.extend(requires)

    fragment = source[proc.source_span[0] : proc.source_span[1]].strip()
    program = Program(
        language="boogie",
        source_ref=filename,
        symbol=proc.name,
        fragment=fragment,
        semantics_model=WHY3_MEMORY_V1.model_id,
        notes="imported by uvil.adapters.boogie (WP VCG, boogie-wp)",
    )

    theories: list[str] = []
    for sort in sorts.values():
        theory = _SORT_THEORY.get(sort)
        if theory and theory not in theories:
            theories.append(theory)
    if not theories:
        theories = ["uvil.core.int@1"]

    spec = Specification(
        profile=BOOGIE_TARGET_PROFILE,
        theories=theories,
        semantics_model=WHY3_MEMORY_V1.model_id,
        subject=proc.name,
        contracts=Contracts(requires=requires, ensures=ensures, modifies=proc.modifies),
    )

    spec_aid = artifact_id(spec)
    program_aid = artifact_id(program)
    obligations: list[Obligation] = []
    for wp in wp_procedure(proc, base_context, sorts, resolve_calls):
        obligations.append(
            _make_obligation(spec_aid, program_aid, wp.context, wp.goal, sorts, theories, filename)
        )
    return ProcedureImport(name=proc.name, program=program, spec=spec, obligations=obligations)


def _make_obligation(
    spec_aid: str,
    program_aid: str,
    context: list[Term],
    goal: Term,
    sorts: dict[str, str],
    theories: list[str],
    filename: str,
) -> Obligation:
    del filename
    var_names = term_vars(goal) | {x for c in context for x in term_vars(c)}
    var_sorts: dict[str, str] = {}
    for v in sorted(var_names):
        base = v[4:-1] if v.startswith("old(") and v.endswith(")") else v
        sort = sorts.get(base)
        if sort is not None:
            var_sorts[v] = _SORT_SMT[sort]
    return Obligation(
        spec_ref=spec_aid,
        program_ref=program_aid,
        semantics_model=WHY3_MEMORY_V1.model_id,
        sequent=Sequent(context=context, goal=goal, var_sorts=var_sorts),
        theories=theories,
        target_profile=BOOGIE_TARGET_PROFILE,
        status="open",
        cost_budget=CostBudget(solver_ms=DEFAULT_SOLVER_MS),
        origin_backend="boogie-wp",
    )
