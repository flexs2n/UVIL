"""Shadow-set evaluation (R4): vacuity probes over a spec's shadow hypotheses.

Operational semantics (pinned here and by tests; failures only *downgrade*):

The probe context is the spec's `contracts.requires` + `contracts.invariants`.
For each shadow hypothesis:

- `expect="refute"` (the counter-hypothesis must NOT be implied by the spec):
  probe `context ∧ ¬formula`.
    - `sat`   ⇒ alignment OK: the spec leaves room for the counter-hypothesis.
    - `unsat` ⇒ the spec forces the hypothesis ⇒ vacuity.
- `expect="accept"` (the expected behavior must be reachable): probe
  `context ∧ formula`.
    - `sat`   ⇒ OK: the expected behavior is reachable.
    - `unsat` ⇒ the spec vacuously excludes the expected behavior.

A vacuity finding emits an I7 `kind="vacuous"` plus an I6 `kind="counterspec"`
whose `counter_spec` is the shadow formula itself (a strengthening witness) and
whose backend witness carries format `shadow-probe`. `unknown`/`timeout` probes
emit an I7 of that kind and are never treated as a pass; an unencodable
(opaque) shadow formula emits a `parse` I7. Shadow evaluation never upgrades a
guarantee - it only reports vacuity.

Boogie-imported specs never carry shadows (authored I2s do). `check()`'s
signature is unchanged: shadows run through `evaluate_shadows` (library API) or
the `uvil shadows` CLI command. Probe obligations are tagged
`origin_backend="shadow-probe"`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..adapters.smt.backends import SmtVerdict
from ..adapters.smt.cex import UNVERIFIED_PREFIX
from ..adapters.smt.encode import OpaqueTermError
from ..artifacts import Counterexample, Diagnostic, Obligation, Specification, artifact_id
from ..artifacts.counterexample import BackendWitness, SharedRender
from ..artifacts.diagnostic import Loc
from ..artifacts.obligation import CostBudget, Sequent
from ..artifacts.terms import Term, t_not
from .core import SmtBackend

DEFAULT_SHADOW_BUDGET_MS = 2000
SHADOW_BACKEND_TAG = "shadow-probe"

ShadowStatus = Literal["ok", "vacuous", "unknown", "timeout", "parse"]

_VACUOUS_DETAIL = {
    "refute": (
        "probe (context AND NOT formula) is unsat: the spec forces the "
        "counter-hypothesis (vacuous spec)"
    ),
    "accept": (
        "probe (context AND formula) is unsat: the spec vacuously excludes the expected behavior"
    ),
}


@dataclass
class ShadowOutcome:
    """Per-shadow-hypothesis result (machine summary row)."""

    name: str
    expect: str
    status: ShadowStatus
    detail: str


@dataclass
class ShadowResult:
    spec: Specification
    outcomes: list[ShadowOutcome] = field(default_factory=list)
    probes: list[Obligation] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    counterexamples: list[Counterexample] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no probe found vacuity and none was inconclusive -
        unknown/timeout/parse never count as a pass; an empty shadow set is
        trivially aligned."""
        return all(o.status == "ok" for o in self.outcomes)


def _probe_obligation(spec: Specification, formula: Term, expect: str, name: str) -> Obligation:
    """Build the probe as a validity question `context ⊢ goal`.

    The SMT encoder asserts `(not goal)`, so a `sat` verdict means the goal's
    negation is satisfiable in the context. Both probes are therefore phrased
    so that `sat` = alignment OK:
    - refute: goal = formula      -> encoder checks context ∧ ¬formula
    - accept: goal = ¬formula     -> encoder checks context ∧ formula
    """
    context = [*spec.contracts.requires, *spec.contracts.invariants]
    goal = formula if expect == "refute" else t_not(formula)
    return Obligation(
        spec_ref=artifact_id(spec),
        program_ref=f"{SHADOW_BACKEND_TAG}:{name}",
        semantics_model=spec.semantics_model,
        sequent=Sequent(context=context, goal=goal),
        theories=list(spec.theories),
        target_profile=spec.profile,
        status="open",
        cost_budget=CostBudget(solver_ms=DEFAULT_SHADOW_BUDGET_MS),
        origin_backend=SHADOW_BACKEND_TAG,
    )


def _vacuous_artifacts(
    obl: Obligation, name: str, expect: str, formula: Term
) -> tuple[Diagnostic, Counterexample]:
    detail = _VACUOUS_DETAIL[expect]
    diagnostic = Diagnostic(
        obligation_ref=artifact_id(obl),
        kind="vacuous",
        loc=Loc(symbol=name),
        native_message=f"shadow {name!r} (expect={expect}): {detail}",
    )
    counterexample = Counterexample(
        obligation_ref=artifact_id(obl),
        kind="counterspec",
        counter_spec=formula,
        shared_render=SharedRender(
            human_summary=f"{UNVERIFIED_PREFIX}\nshadow {name!r}: {detail}",
        ),
        backend_witness=BackendWitness(format=SHADOW_BACKEND_TAG, payload=None),
    )
    return diagnostic, counterexample


def _unpassable_diagnostic(
    obl: Obligation, name: str, expect: str, kind: Literal["unknown", "timeout"], budget: int
) -> Diagnostic:
    return Diagnostic(
        obligation_ref=artifact_id(obl),
        kind=kind,
        loc=Loc(symbol=name),
        native_message=(
            f"shadow {name!r} (expect={expect}): probe returned {kind} within "
            f"budget {budget}ms; alignment unestablished (never a pass)"
        ),
    )


def _classify(verdict: SmtVerdict) -> ShadowStatus:
    mapping: dict[str, ShadowStatus] = {
        "sat": "ok",
        "unsat": "vacuous",
        "unknown": "unknown",
        "timeout": "timeout",
    }
    return mapping[verdict.status]


def evaluate_shadows(
    spec: Specification,
    backend: str = "z3",
    timeout_ms: int | None = None,
) -> ShadowResult:
    """Evaluate the spec's shadow set against an SMT backend (R4)."""
    engine = SmtBackend(backend)
    result = ShadowResult(spec=spec)
    for shadow in spec.shadows:
        obl = _probe_obligation(spec, shadow.formula, shadow.expect, shadow.name)
        result.probes.append(obl)
        budget = timeout_ms or obl.cost_budget.solver_ms or DEFAULT_SHADOW_BUDGET_MS
        try:
            verdict = engine.run(obl, budget)
        except (OpaqueTermError, ValueError) as e:
            # Unencodable shadow formula: fail loud for this probe, never a pass.
            native = getattr(e, "native_message", None) or str(e)
            result.diagnostics.append(
                Diagnostic(
                    obligation_ref=artifact_id(obl),
                    kind="parse",
                    loc=Loc(symbol=shadow.name),
                    native_message=f"shadow {shadow.name!r}: {native}",
                )
            )
            result.outcomes.append(
                ShadowOutcome(name=shadow.name, expect=shadow.expect, status="parse", detail=native)
            )
            continue

        status = _classify(verdict)
        if status == "ok":
            result.outcomes.append(
                ShadowOutcome(
                    name=shadow.name,
                    expect=shadow.expect,
                    status="ok",
                    detail=f"probe is {verdict.status}: alignment holds",
                )
            )
        elif status == "vacuous":
            diagnostic, counterexample = _vacuous_artifacts(
                obl, shadow.name, shadow.expect, shadow.formula
            )
            result.diagnostics.append(diagnostic)
            result.counterexamples.append(counterexample)
            result.outcomes.append(
                ShadowOutcome(
                    name=shadow.name,
                    expect=shadow.expect,
                    status="vacuous",
                    detail=_VACUOUS_DETAIL[shadow.expect],
                )
            )
        else:
            assert status in ("unknown", "timeout")  # "parse" is handled in the except arm
            result.diagnostics.append(
                _unpassable_diagnostic(obl, shadow.name, shadow.expect, status, budget)
            )
            result.outcomes.append(
                ShadowOutcome(
                    name=shadow.name,
                    expect=shadow.expect,
                    status=status,
                    detail=f"probe returned {status}; alignment unestablished",
                )
            )
    return result
