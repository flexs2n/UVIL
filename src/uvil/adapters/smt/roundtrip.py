"""D2 round-trip validation service: z3-AST -> Term reconstruction.

Pipeline: `encode_assertions(obl)` (the M1 encoder) -> `z3.Solver.from_string`
-> walk `solver.assertions()` -> reconstruct shared-theory Terms -> diff against
the original obligation in canonical-JSON normal form.

Discovery findings (pinned by tests, encoded in the mapping below):
- `=>` parses to `Z3_OP_IMPLIES` and survives as `implies`; `-` is split by
  arity: binary `Z3_OP_SUB` -> `sub`, unary `Z3_OP_UMINUS` -> `neg`.
- `div`/`mod` -> `Z3_OP_IDIV`/`Z3_OP_MOD`; `/` over Reals -> `Z3_OP_DIV`.
- Reals are rationals in z3: `2.5` parses to `5/2`; reconstruction converts
  back to the original float.
- Bound variables are de Bruijn `(:var k)`; names/sorts ARE recoverable from
  the enclosing `QuantifierRef` (`var_name(i)`/`var_sort(i)` in declaration
  order). Z3 numbers de Bruijn indices from the innermost scope with the LAST
  declared variable at index 0, so within one quantifier binding (v0..vn-1)
  de Bruijn k resolves to name `v[n-1-k]`. Our core language binds exactly one
  variable per quantifier (`t_forall`/`t_exists` args `[name, sort, body]`);
  multi-var quantifiers are therefore divergences, not silent passes.
- Sorts are converted back to SMT-LIB syntax: `Array(Int, Int)` ->
  `(Array Int Int)`, `Seq(Int)` -> `(Seq Int)`.
- Unmapped z3 constructs (e.g. `Z3_OP_CONST_ARRAY`, `seq.unit` introduced by
  parser normalization) are recorded as divergences - never silently passed.

The final assertion of the encoded script is `(not goal)`; stripping that outer
`not` recovers the goal. Comparison is over canonical JSON (sorted keys) of the
reconstructed context (order-insensitive: sorted canonical strings) and goal.

`roundtrip_validate` is evidence, not a gate: a divergent I9 `Translation`
(`soundness_discipline="lossy"`, divergent strings in
`residuals.dropped_fragments`) is recorded and surfaces in the run summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...artifacts import Obligation, Translation, artifact_id, sha256_hex
from ...artifacts.terms import Term
from ...artifacts.translation import Residuals
from .encode import encode_assertions

TARGET_KIND = "smt-lib2-assertions"


@dataclass
class RoundtripResult:
    lossless: bool
    divergences: list[str] = field(default_factory=list)
    translation: Translation = field(
        default_factory=lambda: Translation(
            source_artifact="",
            target_artifact="",
            source_kind="obligation",
            target_kind=TARGET_KIND,
            soundness_discipline="lossy",
        )
    )


class _Reconstructor:
    """z3 AST -> shared-theory Term reconstruction with divergence recording."""

    def __init__(self) -> None:
        import z3  # type: ignore[import-untyped]

        self._z3 = z3
        self.divergences: list[str] = []
        self._kind_to_op: dict[int, str] = {
            z3.Z3_OP_AND: "and",
            z3.Z3_OP_OR: "or",
            z3.Z3_OP_NOT: "not",
            z3.Z3_OP_IMPLIES: "implies",
            z3.Z3_OP_EQ: "eq",
            z3.Z3_OP_DISTINCT: "neq",
            z3.Z3_OP_LT: "lt",
            z3.Z3_OP_LE: "le",
            z3.Z3_OP_GT: "gt",
            z3.Z3_OP_GE: "ge",
            z3.Z3_OP_ADD: "add",
            z3.Z3_OP_SUB: "sub",
            z3.Z3_OP_UMINUS: "neg",
            z3.Z3_OP_MUL: "mul",
            z3.Z3_OP_IDIV: "intdiv",
            z3.Z3_OP_DIV: "realdiv",
            z3.Z3_OP_MOD: "mod",
            z3.Z3_OP_ITE: "ite",
            z3.Z3_OP_SELECT: "select",
            z3.Z3_OP_STORE: "store",
            z3.Z3_OP_SEQ_LENGTH: "seq.len",
            z3.Z3_OP_SEQ_NTH: "seq.nth",
            z3.Z3_OP_SEQ_EMPTY: "seq.empty",
        }

    def sort_str(self, sort: Any) -> str:
        """z3 Sort -> SMT-LIB sort string (the Term convention)."""
        z3 = self._z3
        k = sort.kind()
        if k == z3.Z3_ARRAY_SORT:
            domain = " ".join(self.sort_str(sort.domain(i)) for i in range(sort.dimensions()))
            return f"(Array {domain} {self.sort_str(sort.range())})"
        if k == z3.Z3_SEQ_SORT:
            return f"(Seq {self.sort_str(sort.basis())})"
        return str(sort)

    def diverge(self, message: str) -> None:
        self.divergences.append(message)

    def reconstruct(self, e: Any, bound: list[list[str]]) -> Term:
        z3 = self._z3
        if z3.is_quantifier(e):
            return self._quantifier(e, bound)
        if z3.is_var(e):
            return self._bound_var(z3.get_var_index(e), bound, e)
        kind = e.decl().kind()
        if kind == z3.Z3_OP_TRUE:
            return Term(op="const", args=[True])
        if kind == z3.Z3_OP_FALSE:
            return Term(op="const", args=[False])
        if z3.is_int_value(e):
            return Term(op="const", args=[int(e.as_string())])
        if z3.is_rational_value(e):
            num = int(e.numerator().as_string())
            den = int(e.denominator().as_string())
            return Term(op="const", args=[num / den])
        if kind == z3.Z3_OP_UNINTERPRETED and e.num_args() == 0:
            return Term(op="var", args=[e.decl().name()])
        op = self._kind_to_op.get(kind)
        if op is None:
            self.diverge(
                f"unmapped z3 construct: decl={e.decl().name()!r} kind={kind} sexpr={e.sexpr()}"
            )
            return Term(op="const", args=[f"!unmapped:{kind}"])
        args: list[Any] = [self.reconstruct(c, bound) for c in e.children()]
        return Term(op=op, args=args)

    def _quantifier(self, e: Any, bound: list[list[str]]) -> Term:
        op = "forall" if e.is_forall() else "exists"
        names = [e.var_name(i) for i in range(e.num_vars())]
        if e.num_vars() != 1:
            self.diverge(
                f"quantifier with {e.num_vars()} bound variables "
                f"({', '.join(names)}); the core language binds one per quantifier"
            )
        sorts = [self.sort_str(e.var_sort(i)) for i in range(e.num_vars())]
        body = self.reconstruct(e.body(), [*bound, names])
        return Term(op=op, args=[names[0], sorts[0], body])

    def _bound_var(self, index: int, bound: list[list[str]], e: Any) -> Term:
        remaining = index
        for frame in reversed(bound):
            if remaining < len(frame):
                return Term(op="var", args=[frame[len(frame) - 1 - remaining]])
            remaining -= len(frame)
        self.diverge(f"unresolvable de Bruijn index {index}; sexpr={e.sexpr()}")
        return Term(op="const", args=[f"!unbound:{index}"])


def _canonical(term: Term) -> str:
    from ...artifacts import canonical_json_bytes

    return canonical_json_bytes(term.model_dump(mode="json")).decode("utf-8")


def roundtrip_validate(obl: Obligation) -> RoundtripResult:
    """Encode, parse back with z3, reconstruct Terms, and diff canonical forms."""
    import z3

    script = encode_assertions(obl)
    recon = _Reconstructor()
    solver = z3.Solver()
    solver.from_string(script)
    assertions = list(solver.assertions())

    if not assertions:
        recon.diverge("encoded script produced no assertions")
        recon_context: list[Term] = []
        recon_goal: Term | None = None
    else:
        recon_context = [recon.reconstruct(a, []) for a in assertions[:-1]]
        last = recon.reconstruct(assertions[-1], [])
        # the final assert is `(not goal)`: strip the outer not to recover the goal
        if last.op == "not" and last.args and isinstance(last.args[0], Term):
            recon_goal = last.args[0]
        else:
            recon.diverge(f"final assertion is not (not goal): {_canonical(last)}")
            recon_goal = None

    if recon_goal is not None and _canonical(recon_goal) != _canonical(obl.sequent.goal):
        recon.diverge(
            "goal mismatch: "
            f"original={_canonical(obl.sequent.goal)} "
            f"reconstructed={_canonical(recon_goal)}"
        )

    original = sorted(_canonical(t) for t in obl.sequent.context)
    reconstructed = sorted(_canonical(t) for t in recon_context)
    if original != reconstructed:
        original_set, reconstructed_set = set(original), set(reconstructed)
        for c in original_set - reconstructed_set:
            recon.diverge(f"context term not preserved: {c}")
        for c in reconstructed_set - original_set:
            recon.diverge(f"context term not recovered: {c}")

    divergences = sorted(set(recon.divergences))
    lossless = not divergences
    translation = Translation(
        source_artifact=artifact_id(obl),
        target_artifact=f"{TARGET_KIND}:{sha256_hex(script.encode('utf-8'))}",
        source_kind="obligation",
        target_kind=TARGET_KIND,
        mapping=[
            {"source": f"sequent.context[{i}]", "target": f"assert[{i}]"}
            for i in range(len(obl.sequent.context))
        ]
        + [{"source": "sequent.goal", "target": f"assert[{len(obl.sequent.context)}].not"}],
        soundness_discipline="roundtrip-validated" if lossless else "lossy",
        residuals=Residuals(dropped_fragments=divergences),
        notes="z3 parse round-trip of encode_assertions output (D2 evidence, non-gating)",
    )
    return RoundtripResult(lossless=lossless, divergences=divergences, translation=translation)
