"""ESBMC check dispatch: C harnesses -> I8 run + I6 traces + I7 diagnostics.

Mirrors `check_lean` / `check.core.check` with the model-checking discipline
of the M4 plan:

- one harness = one C source + the I4 obligations imported from it (corpus
  discipline: one assert per harness; multi-assert harnesses share the
  file-level verdict - which can never upgrade anything, see below);
- `esbmc_status` is the single TOTAL verdict mapping: verified/violated/
  unknown all leave obligations `open`, timeout maps to `timeout` - a
  model-checking result NEVER discharges a deductive obligation and NEVER
  refutes one;
- a violation emits the I6 Trace built from ESBMC's JSON report (the M2
  pre-registered `backend_witness.format="esbmc-trace"`) plus an I7 `unproved`
  stating it is not a deductive refutation;
- unknown/timeout emit I7 `unknown`/`timeout`; a violated harness whose JSON
  report is unexpectedly missing is downgraded to `unknown` with an I7
  (fail loud, never fabricated evidence);
- `record_esbmc` appends G1 (model-checking run record with tool attestation)
  when at least one harness verified, G0 otherwise. Obligations checked
  deductively by SMT elsewhere keep their own guarantee classes - no
  cross-upgrade in either direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..adapters.esbmc.backend import (
    ESBMC_RELEASE_TAG,
    PINNED_ESBMC,
    EsbmcBackend,
    EsbmcVerdict,
    esbmc_status,
)
from ..adapters.esbmc.cex import ESBMC_TRACE_FORMAT, build_trace
from ..artifacts import (
    Counterexample,
    Diagnostic,
    Obligation,
    Run,
    Verdict,
    artifact_id,
)
from ..artifacts.run import ToolDescriptor
from ..ledger import Attestation, Ledger
from ..store import ContentStore


@dataclass
class CHarness:
    """One C harness paired with the obligations imported from it."""

    source: str
    filename: str
    obligations: list[Obligation]


@dataclass
class EsbmcCheckResult:
    obligations: list[Obligation] = field(default_factory=list)
    counterexamples: list[Counterexample] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    run: Run | None = None


def check_esbmc(
    harnesses: list[CHarness],
    timeout_s: float | None = None,
    multi_property: bool = False,
) -> EsbmcCheckResult:
    """Run every harness under the pinned ESBMC and map verdicts onto its
    obligations. Raises `EsbmcNotInstalled` when the binary is absent
    (skip-if-absent) and `EsbmcVersionMismatch` on a present-but-unpinned
    binary (hard error)."""
    if not harnesses:
        raise ValueError("check_esbmc() requires at least one harness")
    backend = EsbmcBackend()

    result = EsbmcCheckResult()
    verdicts: list[Verdict] = []
    flags = ["--generate-json-report", *(["--multi-property"] if multi_property else [])]

    for harness in harnesses:
        verdict = backend.run_source(harness.source, harness.filename, timeout_s=timeout_s)
        status = esbmc_status(verdict)
        if verdict.status == "violated" and verdict.report_json is None:
            # a violation with no machine-readable report: fail loud (R3), not
            # fabricated evidence - record unknown with an explanatory I7
            verdict = _unknown_verdict(verdict)
            status = esbmc_status(verdict)
        trace = (
            build_trace(harness.obligations[0], verdict.report_json or "")
            if verdict.status == "violated" and harness.obligations
            else None
        )
        for obl in harness.obligations:
            verdicts.append(
                Verdict(
                    obligation_ref=artifact_id(obl),
                    status=status,
                    time_ms=verdict.time_ms,
                    note=f"model-checking: {verdict.status} (bounded C semantics)",
                )
            )
            result.obligations.append(obl.model_copy(update={"status": status}))
            if trace is not None:
                result.counterexamples.append(
                    trace.model_copy(update={"obligation_ref": artifact_id(obl)})
                )
        result.diagnostics.extend(_diagnostics(harness, verdict))

    verified = sum(1 for v in verdicts if (v.note or "").startswith("model-checking: verified"))
    seen: dict[str, int] = {}
    for v in verdicts:
        seen[v.status] = seen.get(v.status, 0) + 1
    result.run = Run(
        tool=ToolDescriptor(name="esbmc", version=PINNED_ESBMC, flags=flags),
        config={
            "release_tag": ESBMC_RELEASE_TAG,
            "timeout_s": timeout_s,
            "multi_property": multi_property,
            "verdict_semantics": (
                "model checking (bounded); never discharges or refutes deductive obligations"
            ),
            "trace_format": ESBMC_TRACE_FORMAT,
        },
        verdicts=verdicts,
        resource_stats={
            "harnesses": len(harnesses),
            "model_checking_verified": verified,
            **{f"status_{k}": n for k, n in sorted(seen.items())},
        },
    )
    return result


def _unknown_verdict(verdict: EsbmcVerdict) -> EsbmcVerdict:
    return EsbmcVerdict(
        status="unknown",
        esbmc_version=verdict.esbmc_version,
        time_ms=verdict.time_ms,
        raw_output=verdict.raw_output
        + "\nviolation reported without the JSON report (fail loud, R3)",
        report_json=None,
    )


def _diagnostics(harness: CHarness, verdict: EsbmcVerdict) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for obl in harness.obligations:
        ref = artifact_id(obl)
        if verdict.status == "violated":
            out.append(
                Diagnostic(
                    obligation_ref=ref,
                    kind="unproved",
                    native_message=(
                        "model-checking violation: ESBMC found a counterexample "
                        "execution (I6 trace attached). This is a bounded "
                        "model-checking witness, not a deductive refutation - "
                        f"the obligation stays open (R1):\n{verdict.raw_output}"
                    ),
                )
            )
        elif verdict.status == "unknown":
            out.append(
                Diagnostic(
                    obligation_ref=ref,
                    kind="unknown",
                    native_message=(
                        "esbmc returned no verdict within budget "
                        f"({ESBMC_RELEASE_TAG}); obligation left open "
                        "(never discharged, never refuted):\n"
                        f"{verdict.raw_output}"
                    ),
                )
            )
        elif verdict.status == "timeout":
            out.append(
                Diagnostic(
                    obligation_ref=ref,
                    kind="timeout",
                    native_message=(
                        "esbmc exceeded the subprocess budget (--timeout is "
                        "unimplemented on Windows; budget enforced by the "
                        "subprocess layer); obligation left open"
                    ),
                )
            )
    return out


def record_esbmc(result: EsbmcCheckResult, store: ContentStore, ledger: Ledger) -> list[str]:
    """Store produced artifacts in the CAS; append the guarantee-class entry.

    G1 (model-checking run record with tool attestation) when at least one
    harness verified; G0 when none did - a run with zero verified harnesses
    must not fabricate a guarantee (R1). Model-checking G1 never upgrades or
    downgrades the deductive guarantee classes of other backends.
    """
    if result.run is None:
        raise ValueError("record_esbmc() requires an EsbmcCheckResult with a run")
    run_aid = store.put_artifact(result.run)
    refs = [run_aid]
    for obl in result.obligations:
        refs.append(store.put_artifact(obl))
    for cex in result.counterexamples:
        refs.append(store.put_artifact(cex))
    for diag in result.diagnostics:
        refs.append(store.put_artifact(diag.model_copy(update={"run_ref": run_aid})))

    verified = sum(
        1 for v in result.run.verdicts if (v.note or "").startswith("model-checking: verified")
    )
    if verified:
        ledger.append(
            refs,
            guarantee_class="G1",
            attestation=Attestation(
                tool="esbmc",
                version=PINNED_ESBMC,
                detail=(
                    f"model-checking G1: {verified} harness(es) verified by the "
                    f"pinned ESBMC {ESBMC_RELEASE_TAG} binary; bounded "
                    "model-checking run record - never discharges or refutes "
                    "deductive obligations (no cross-upgrade)"
                ),
            ),
        )
    else:
        ledger.append(
            refs,
            guarantee_class="G0",
            attestation=Attestation(
                tool="esbmc",
                version=PINNED_ESBMC,
                detail=(
                    "no model-checking verification recorded; run recorded without guarantee (R1)"
                ),
            ),
        )
    return refs
