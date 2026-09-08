"""Lean check dispatch: I4 obligations -> I5 kernel-attested proofs + I8 run.

The code path to I4 `discharged` via Lean is EXCLUSIVELY a kernel-attested
proof (exit-0 compile of the standalone theorem file under the pinned
toolchain) - R1 in practice:
- failed/timeout proof search  -> obligation stays `open` + I7
  (`unproved`/`timeout`); never `refuted` (a failed proof search produces no
  counterexample) and never `discharged`;
- encoding failure (term outside the omega subset) -> I7 `semantic-mismatch`
  with the verbatim SMT sexpr; obligation stays open;
- every attested obligation carries an I5 `Proof` whose `BackendDescriptor.
  kernel_hash` is sha256 over the exact standalone proof-file bytes + the
  toolchain id - replayable offline with the pinned toolchain alone.

`record_lean` CAS-stores the artifacts and appends the guarantee-class entry:
G1 (kernel attestation) when at least one proof was attested, G0 (processed,
no guarantee) otherwise - a run with zero attested proofs must not fabricate
a kernel guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..adapters.lean.backend import (
    LEAN_BATCH_SIZE,
    PINNED_LEAN,
    TOOLCHAIN_ID,
    LeanBackend,
    LeanVerdict,
    lean_status,
)
from ..adapters.lean.encode import UnsupportedTermError, to_lean_theorem
from ..artifacts import (
    Diagnostic,
    Obligation,
    Proof,
    Run,
    Verdict,
    artifact_id,
    sha256_hex,
)
from ..artifacts.proof import BackendDescriptor, Checker, ProofPayload
from ..artifacts.run import KernelAttestation, ToolDescriptor
from ..ledger import Attestation, Ledger
from ..store import ContentStore

CHECKER_ENTRY = "uvil-check lean4"


@dataclass
class LeanCheckResult:
    obligations: list[Obligation] = field(default_factory=list)
    proofs: list[Proof] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    run: Run | None = None


def check_lean(
    obligations: list[Obligation],
    check_timeout_s: float | None = None,
) -> LeanCheckResult:
    """Encode obligations as Lean theorems and attest them with the pinned
    kernel. Raises `LeanNotInstalled` when elan is absent (skip-if-absent)."""
    if not obligations:
        raise ValueError("check_lean() requires at least one obligation")
    backend = LeanBackend(check_timeout_s=check_timeout_s)

    result = LeanCheckResult()
    verdicts: list[Verdict] = []
    kernel_hashes: list[str] = []

    encoded: list[str] = []
    encode_errors: dict[int, UnsupportedTermError] = {}
    for i, obl in enumerate(obligations):
        try:
            encoded.append(to_lean_theorem(obl))
        except UnsupportedTermError as e:
            encode_errors[i] = e

    # batch + compile (only obligations that encoded)
    checkable = [i for i in range(len(obligations)) if i not in encode_errors]
    verdict_map: dict[int, LeanVerdict] = {}
    if checkable:
        raw = backend.check_batch([encoded[i] for i in checkable])
        verdict_map = dict(zip(checkable, raw, strict=True))

    # assemble strictly in input order (the run's verdict list is the
    # machine-readable record; ordering must be deterministic)
    for i, obl in enumerate(obligations):
        error = encode_errors.get(i)
        if error is not None:
            verdicts.append(Verdict(obligation_ref=artifact_id(obl), status="open"))
            result.obligations.append(obl)
            result.diagnostics.append(
                Diagnostic(
                    obligation_ref=artifact_id(obl),
                    kind="semantic-mismatch",
                    native_message=(
                        f"term outside the Lean/omega subset; obligation left open "
                        f"(fail-loud R3): {error.native_message}"
                    ),
                )
            )
            continue

        theorem = encoded[i]
        lean_verdict = verdict_map[i]
        status = lean_status(lean_verdict)
        verdicts.append(
            Verdict(
                obligation_ref=artifact_id(obl),
                status=status,
                time_ms=lean_verdict.time_ms,
            )
        )
        result.obligations.append(obl.model_copy(update={"status": status}))
        if lean_verdict.status == "attested":
            proof = Proof(
                obligation_ref=artifact_id(obl),
                backend=BackendDescriptor(
                    name="lean4",
                    version=PINNED_LEAN,
                    kernel_hash=lean_verdict.file_digest,
                ),
                payload=ProofPayload(format="lean-proof-term", inline=theorem),
                checker=Checker(entry=CHECKER_ENTRY, independent=True, version=PINNED_LEAN),
            )
            result.proofs.append(proof)
            kernel_hashes.append(lean_verdict.file_digest)
        elif lean_verdict.status == "failed":
            result.diagnostics.append(
                Diagnostic(
                    obligation_ref=artifact_id(obl),
                    kind="unproved",
                    native_message=(
                        "the pinned Lean kernel rejected the generated theorem "
                        "(obligation left open; a failed proof search is never a "
                        f"refutation):\n{lean_verdict.native_output}"
                    ),
                )
            )
        else:
            result.diagnostics.append(
                Diagnostic(
                    obligation_ref=artifact_id(obl),
                    kind="timeout",
                    native_message=(
                        "lean compile exceeded the time budget; obligation left "
                        "open (never discharged, never refuted)"
                    ),
                )
            )

    kernel_attestations = [
        KernelAttestation(backend="lean4", kernel_hash=h, checked=True) for h in kernel_hashes
    ]
    counts = {"attested": len(result.proofs)}
    for v in verdicts:
        counts[v.status] = counts.get(v.status, 0) + 1
    result.run = Run(
        tool=ToolDescriptor(name="lean4", version=PINNED_LEAN, flags=[]),
        config={
            "toolchain": TOOLCHAIN_ID,
            "check_timeout_s": check_timeout_s,
            "batch_size": LEAN_BATCH_SIZE,
        },
        verdicts=verdicts,
        resource_stats={
            "obligations": len(verdicts),
            **{f"status_{k}": v for k, v in sorted(counts.items())},
        },
        kernel_attestations=kernel_attestations,
    )
    return result


def record_lean(result: LeanCheckResult, store: ContentStore, ledger: Ledger) -> list[str]:
    """Store produced artifacts in the CAS; append the guarantee-class entry.

    G1 (kernel attestation) when at least one proof was attested; G0 when the
    run produced no proof (a run with zero attested proofs must not fabricate
    a kernel guarantee - R1).
    """
    if result.run is None:
        raise ValueError("record_lean() requires a LeanCheckResult with a run")
    run_aid = store.put_artifact(result.run)
    refs = [run_aid]
    for obl in result.obligations:
        refs.append(store.put_artifact(obl))
    for proof in result.proofs:
        refs.append(store.put_artifact(proof))
    for diag in result.diagnostics:
        refs.append(store.put_artifact(diag.model_copy(update={"run_ref": run_aid})))

    if result.proofs:
        # the run-level attestation commits to every per-obligation kernel hash
        combined = sha256_hex(
            "\n".join(sorted(p.backend.kernel_hash or "" for p in result.proofs)).encode("utf-8")
        )
        detail = (
            f"kernel-attested G1: {len(result.proofs)} proof(s) accepted by the "
            f"pinned Lean kernel ({TOOLCHAIN_ID}); offline-replayable from the "
            "stored I5 payloads"
        )
        ledger.append(
            refs,
            guarantee_class="G1",
            attestation=Attestation(
                tool="lean4",
                version=PINNED_LEAN,
                kernel_hash=combined,
                detail=detail,
            ),
        )
    else:
        ledger.append(
            refs,
            guarantee_class="G0",
            attestation=Attestation(
                tool="lean4",
                version=PINNED_LEAN,
                detail="no Lean proofs attested; run recorded without guarantee (R1)",
            ),
        )
    return refs
