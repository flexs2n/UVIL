"""Check dispatch, I8 run construction, and G1 ledger recording."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..adapters.smt.backends import (
    PINNED_Z3,
    Cvc5Backend,
    SmtVerdict,
    Z3Backend,
    verdict_status,
)
from ..adapters.smt.cex import build_counterexample
from ..adapters.smt.encode import OpaqueTermError, encode_assertions, encode_script
from ..adapters.smt.roundtrip import roundtrip_validate
from ..artifacts import (
    Counterexample,
    Diagnostic,
    Obligation,
    Run,
    Translation,
    Verdict,
    artifact_id,
    canonical_bytes,
    sha256_hex,
)
from ..artifacts.run import ToolDescriptor
from ..artifacts.translation import Residuals
from ..ledger import Attestation, Ledger
from ..store import ContentStore

_G1_DETAIL = "solver-verdict G1: no certificates attached (Alethe/LFSC upgrade path M4+)"

Discipline = str  # "none" | "roundtrip" (validated at runtime, fail-loud)


@dataclass
class CheckResult:
    obligations: list[Obligation] = field(default_factory=list)
    counterexamples: list[Counterexample] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    translations: list[Translation] = field(default_factory=list)
    run: Run | None = None


class SmtBackend:
    """Minimal common interface so `check` needs no per-backend branching."""

    def __init__(self, backend: str) -> None:
        if backend == "z3":
            self._z3: Z3Backend | None = Z3Backend()
            self._cvc5: Cvc5Backend | None = None
            self.version = PINNED_Z3
        elif backend == "cvc5":
            self._z3 = None
            self._cvc5 = Cvc5Backend()
            self.version = self._cvc5.version()
        else:
            raise ValueError(f"unknown backend: {backend!r} (expected 'z3' or 'cvc5')")

    def run(self, obl: Obligation, budget: int | None) -> SmtVerdict:
        if self._z3 is not None:
            return self._z3.run(encode_assertions(obl), solver_ms=budget)
        assert self._cvc5 is not None
        return self._cvc5.run(encode_script(obl), solver_ms=budget)


def check(
    obligations: list[Obligation],
    backend: str = "z3",
    timeout_ms: int | None = None,
    discipline: Discipline = "none",
) -> CheckResult:
    """Dispatch obligations to an SMT backend; collect verdicts, I6s, I7s, I8.

    `discipline="roundtrip"` additionally runs the D2 round-trip validation on
    every obligation before solving: the resulting I9 `Translation` is recorded
    as evidence (non-gating by design - divergences never block the check).
    """
    if discipline not in ("none", "roundtrip"):
        raise ValueError(f"unknown discipline: {discipline!r} (expected 'none' or 'roundtrip')")
    if not obligations:
        raise ValueError("check() requires at least one obligation")
    engine = SmtBackend(backend)
    result = CheckResult()
    verdicts: list[Verdict] = []

    for obl in obligations:
        if discipline == "roundtrip":
            try:
                result.translations.append(roundtrip_validate(obl).translation)
            except (OpaqueTermError, ValueError) as e:
                # Fail loud as evidence: record a lossy I9 and keep checking.
                result.translations.append(
                    Translation(
                        source_artifact=artifact_id(obl),
                        target_artifact=f"roundtrip-error:{sha256_hex(str(e).encode('utf-8'))}",
                        source_kind="obligation",
                        target_kind="smt-lib2-assertions",
                        soundness_discipline="lossy",
                        residuals=Residuals(dropped_fragments=[str(e)]),
                        notes="round-trip validation could not run",
                    )
                )
        budget = timeout_ms or obl.cost_budget.solver_ms
        try:
            verdict = engine.run(obl, budget)
            diagnostic = None
        except (OpaqueTermError, ValueError) as e:
            verdict = None
            native = getattr(e, "native_message", None) or str(e)
            diagnostic = Diagnostic(
                obligation_ref=artifact_id(obl),
                kind="parse",
                native_message=native,
            )

        if verdict is not None:
            status = verdict_status(verdict)
            verdicts.append(
                Verdict(obligation_ref=artifact_id(obl), status=status, time_ms=verdict.time_ms)
            )
            result.obligations.append(obl.model_copy(update={"status": status}))
            if verdict.status == "sat" and verdict.model is not None:
                result.counterexamples.append(build_counterexample(obl, verdict.model))
                # A refutation is a first-class failure: emit an I7 `unproved`
                # alongside the I6 witness. Deterministic text - no solver
                # timing or session ids inside the message.
                result.diagnostics.append(
                    Diagnostic(
                        obligation_ref=artifact_id(obl),
                        kind="unproved",
                        native_message=(
                            f"obligation refuted: backend {backend} satisfied the "
                            "negated goal; a counterexample valuation (I6) "
                            "accompanies this diagnostic"
                        ),
                    )
                )
            if verdict.status in ("unknown", "timeout"):
                result.diagnostics.append(
                    Diagnostic(
                        obligation_ref=artifact_id(obl),
                        kind="unknown" if verdict.status == "unknown" else "timeout",
                        native_message=(
                            f"backend {backend} returned {verdict.status} within budget {budget}ms"
                        ),
                    )
                )
        else:
            # The obligation could not be checked at all: it stays open, with the
            # failure attached as an I7 (fail-loud, never silently skipped).
            assert diagnostic is not None
            verdicts.append(Verdict(obligation_ref=artifact_id(obl), status="open"))
            result.obligations.append(obl)
            result.diagnostics.append(diagnostic)

    result.run = Run(
        tool=ToolDescriptor(name=backend, version=engine.version, flags=[]),
        config={"backend": backend, "timeout_ms": timeout_ms, "discipline": discipline},
        verdicts=verdicts,
    )
    return result


def record(result: CheckResult, store: ContentStore, ledger: Ledger) -> list[str]:
    """Store produced artifacts in the CAS; append a solver-verdict G1 entry."""
    if result.run is None:
        raise ValueError("record() requires a CheckResult with a run")
    run_aid = store.put_artifact(result.run)
    refs = [run_aid]
    for obl in result.obligations:
        refs.append(store.put_artifact(obl))
    for cex in result.counterexamples:
        refs.append(store.put_artifact(cex))
    for diag in result.diagnostics:
        refs.append(store.put_artifact(diag.model_copy(update={"run_ref": run_aid})))
    for translation in result.translations:
        if translation is not None:
            refs.append(store.put_artifact(translation))
    ledger.append(
        refs,
        guarantee_class="G1",
        attestation=Attestation(
            tool=result.run.tool.name,
            version=result.run.tool.version,
            kernel_hash=sha256_hex(canonical_bytes(result.run)),
            detail=_G1_DETAIL,
        ),
    )
    return refs
