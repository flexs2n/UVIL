"""SMT-LIB2 encoding of I4 obligations (golden-snapshot target).

`encode_script` is the full, solver-runnable artifact (declarations + assertions
+ `check-sat`/`get-model`/`get-info`). `encode_assertions` is the same prefix
without the trailing commands, for in-process backends that drive assertions
through an API instead of a command stream.

Opaque terms have no shared-theory rendering (`terms.to_smt` raises); the
encoder surfaces that as `OpaqueTermError` so callers emit an I7 and keep the
obligation open - nothing is silently dropped.
"""

from __future__ import annotations

from ...artifacts.obligation import Obligation
from ...artifacts.terms import term_vars

DEFAULT_LOGIC = "ALL"


class OpaqueTermError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.native_message = message


def _assertions(obl: Obligation) -> list[str]:
    from ...artifacts.terms import to_smt

    lines = [f"(assert {to_smt(t)})" for t in obl.sequent.context]
    try:
        lines.append(f"(assert (not {to_smt(obl.sequent.goal)}))")
    except ValueError as e:
        raise OpaqueTermError(str(e)) from e
    return lines


def _declarations(obl: Obligation) -> list[str]:
    names = sorted(
        term_vars(obl.sequent.goal) | {v for c in obl.sequent.context for v in term_vars(c)}
    )
    return [f"(declare-const {n} {obl.sequent.var_sorts.get(n, 'Int')})" for n in names]


def encode_assertions(obl: Obligation) -> str:
    """Declarations + context/goal assertions; no solver commands."""
    lines = [f"(set-logic {DEFAULT_LOGIC})", *_declarations(obl), *_assertions(obl)]
    return "\n".join(lines) + "\n"


def encode_script(obl: Obligation) -> str:
    """Full SMT-LIB2 script: assertions + check-sat + get-model + version probe."""
    tail = ["(check-sat)", "(get-model)", "(get-info :version)"]
    return encode_assertions(obl) + "\n".join(tail) + "\n"
