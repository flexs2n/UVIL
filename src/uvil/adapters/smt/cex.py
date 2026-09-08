"""Solver model -> I6 Counterexample (kind=valuation).

Only scalar values (Int/Bool/Real literals) are extracted into the shared-theory
`valuation` map; the complete raw model text always travels in
`shared_render.smt_lib_valuation` so nothing is lost. The `human_summary` is a
name = value rendering and is permanently marked as unverified.
"""

from __future__ import annotations

from ...artifacts import Counterexample, Obligation
from ...artifacts.counterexample import BackendWitness, SharedRender
from ...artifacts.terms import Term

UNVERIFIED_PREFIX = "[unverified human rendering]"


def _parse_sexpr(text: str) -> list[object]:
    """Tokenize/parse the (define-fun name () Sort Value) entries of a model."""
    tokens = text.replace("(", " ( ").replace(")", " ) ").split()
    entries: list[object] = []
    stack: list[list[object]] = []
    current: list[object] = entries
    for tok in tokens:
        if tok == "(":
            nxt: list[object] = []
            current.append(nxt)
            stack.append(current)
            current = nxt
        elif tok == ")":
            current = stack.pop() if stack else current
        else:
            current.append(tok)
    return entries


def _find_define_funs(node: object) -> list[list[object]]:
    found: list[list[object]] = []
    if isinstance(node, list):
        if node and node[0] == "define-fun":
            found.append(node)
        for child in node:
            if isinstance(child, list):
                found.extend(_find_define_funs(child))
    return found


def _to_const(value: str) -> Term | None:
    if value == "true":
        return Term(op="const", args=[True])
    if value == "false":
        return Term(op="const", args=[False])
    try:
        return Term(op="const", args=[int(value)])
    except ValueError:
        pass
    try:
        return Term(op="const", args=[float(value)])
    except ValueError:
        return None


def parse_model_valuation(model_text: str) -> dict[str, Term]:
    """Extract scalar `define-fun` bindings from a raw SMT-LIB model text."""
    valuation: dict[str, Term] = {}
    for entry in _find_define_funs(_parse_sexpr(model_text)):
        # (define-fun name () Sort Value)
        if len(entry) != 5 or not isinstance(entry[1], str):
            continue
        value = entry[4]
        if isinstance(value, list):
            continue  # non-scalar (array/lambda/ BV concat...) - stays in raw text
        assert isinstance(value, str)
        term = _to_const(value)
        if term is not None:
            valuation[entry[1]] = term
    return valuation


def build_counterexample(obl: Obligation, model_text: str) -> Counterexample:
    valuation = parse_model_valuation(model_text)
    summary = "\n".join(f"{name} = {term_model_value(term)}" for name, term in valuation.items())
    return Counterexample(
        obligation_ref=_obligation_ref(obl),
        kind="valuation",
        valuation=valuation or None,
        shared_render=SharedRender(
            smt_lib_valuation=model_text,
            human_summary=f"{UNVERIFIED_PREFIX}\n{summary}" if valuation else UNVERIFIED_PREFIX,
        ),
        backend_witness=BackendWitness(format="smt-lib2-model", payload=model_text),
    )


def term_model_value(term: Term) -> str:
    if term.op == "const" and term.args:
        value = term.args[0]
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
    return f"<{term.op}>"


def _obligation_ref(obl: Obligation) -> str:
    from ...artifacts import artifact_id

    return artifact_id(obl)
