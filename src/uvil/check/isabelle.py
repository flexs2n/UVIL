"""Isabelle check dispatch: I4 obligations -> HOL twins + I5 proofs + I8 run.

Mirrors `check_lean` with the HOL-facing boundary (`adapters.isabelle.encode`):
- encoding failure (term outside the boundary) -> obligation stays `open` +
  I7 `semantic-mismatch` with the verbatim SMT sexpr + an I9 `lossy`
  `Translation` (the measured downgrade - never hidden, never fabricated);
- failed/timeout proof search -> `open` + I7 `unproved`/`timeout`; never
  `refuted` (a failed proof search produces no counterexample);
- every attested obligation carries an I5 `Proof` with payload
  `format="isabelle-theory"` and `checker.entry="uvil-check isabelle"`
  (independent), whose `kernel_hash` is sha256(theory-file bytes + Isabelle
  version id) - replayable offline with the pinned bundle alone.

`record_isabelle` CAS-stores the artifacts and appends G1 (kernel
attestation) when at least one proof was attested, G0 otherwise - a run with
zero attested proofs must not fabricate a kernel guarantee (R1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..adapters.isabelle.backend import (
    ISABELLE_VERSION_ID,
    PINNED_ISABELLE,
    IsabelleBackend,
    IsabelleVerdict,
    isabelle_status,
)
from ..adapters.isabelle.encode import (
    ISABELLE_BATCH_SIZE,
    TARGET_KIND,
    UnsupportedTermError,
    to_hol_theorem,
)
from ..artifacts import (
    Diagnostic,
    Obligation,
    Proof,
    Run,
    Translation,
    Verdict,
    artifact_id,
    sha256_hex,
)
from ..artifacts.proof import BackendDescriptor, Checker, ProofPayload
from ..artifacts.run import KernelAttestation, ToolDescriptor
from ..artifacts.translation import Residuals
from ..ledger import Attestation, Ledger
from ..store import ContentStore

CHECKER_ENTRY = "uvil-check isabelle"


@dataclass
class IsabelleCheckResult:
    obligations: list[Obligation] = field(default_factory=list)
    proofs: list[Proof] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    translations: list[Translation] = field(default_factory=list)
    run: Run | None = None


def check_isabelle(
    obligations: list[Obligation],
    check_timeout_s: float | None = None,
) -> IsabelleCheckResult:
    """Encode obligations as HOL theorems and attest them with the pinned
    bundle. Raises `IsabelleNotInstalled` when Isabelle is absent
    (skip-if-absent) and `IsabelleVersionMismatch` on a present-but-unpinned
    bundle (hard error)."""
    if not obligations:
        raise ValueError("check_isabelle() requires at least one obligation")
    backend = IsabelleBackend(check_timeout_s=check_timeout_s)

    result = IsabelleCheckResult()
    verdicts: list[Verdict] = []
    theory_digests: list[str] = []

    # encoded[i] stays None exactly when obligation i is outside the HOL-facing
    # boundary - the list stays aligned with `obligations` by position (an
    # encode-error-compressed list misindexes every obligation after the first
    # failure; live-corpus discovery, 2026-09-11)
    encoded: list[str | None] = [None] * len(obligations)
    encode_errors: dict[int, UnsupportedTermError] = {}
    for i, obl in enumerate(obligations):
        try:
            encoded[i] = to_hol_theorem(obl)
        except UnsupportedTermError as e:
            encode_errors[i] = e

    # batch + build (only obligations that encoded)
    checkable = [i for i in range(len(obligations)) if i not in encode_errors]
    verdict_map: dict[int, IsabelleVerdict] = {}
    if checkable:
        to_check = [t for i in checkable if (t := encoded[i]) is not None]
        raw = backend.check_batch(to_check)
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
                        f"term outside the Isabelle/HOL boundary; obligation left "
                        f"open (fail-loud R3): {error.native_message}"
                    ),
                )
            )
            # the measured downgrade: an honest lossy I9 accompanies the I7
            result.translations.append(
                Translation(
                    source_artifact=artifact_id(obl),
                    target_artifact=f"downgrade-error:{sha256_hex(str(error).encode('utf-8'))}",
                    source_kind="obligation",
                    target_kind=TARGET_KIND,
                    soundness_discipline="lossy",
                    residuals=Residuals(dropped_fragments=[error.native_message]),
                    notes="obligation outside the HOL-facing boundary (downgrade rate metric)",
                )
            )
            continue

        theorem = encoded[i]
        assert theorem is not None  # i is not in encode_errors
        verdict = verdict_map[i]
        status = isabelle_status(verdict)
        verdicts.append(
            Verdict(
                obligation_ref=artifact_id(obl),
                status=status,
                time_ms=verdict.time_ms,
            )
        )
        result.obligations.append(obl.model_copy(update={"status": status}))
        if verdict.status == "attested":
            proof = Proof(
                obligation_ref=artifact_id(obl),
                backend=BackendDescriptor(
                    name="isabelle-hol",
                    version=PINNED_ISABELLE,
                    kernel_hash=verdict.theory_digest,
                ),
                payload=ProofPayload(format="isabelle-theory", inline=theorem),
                checker=Checker(entry=CHECKER_ENTRY, independent=True, version=PINNED_ISABELLE),
            )
            result.proofs.append(proof)
            theory_digests.append(verdict.theory_digest)
        elif verdict.status == "failed":
            result.diagnostics.append(
                Diagnostic(
                    obligation_ref=artifact_id(obl),
                    kind="unproved",
                    native_message=(
                        "the pinned Isabelle kernel rejected the generated theorem "
                        "(obligation left open; a failed proof search is never a "
                        f"refutation):\n{verdict.native_output}"
                    ),
                )
            )
        else:
            result.diagnostics.append(
                Diagnostic(
                    obligation_ref=artifact_id(obl),
                    kind="timeout",
                    native_message=(
                        "isabelle build exceeded the time budget; obligation left "
                        "open (never discharged, never refuted)"
                    ),
                )
            )

    kernel_attestations = [
        KernelAttestation(backend="isabelle-hol", kernel_hash=h, checked=True)
        for h in theory_digests
    ]
    counts = {"attested": len(result.proofs)}
    for v in verdicts:
        counts[v.status] = counts.get(v.status, 0) + 1
    result.run = Run(
        tool=ToolDescriptor(name="isabelle-hol", version=PINNED_ISABELLE, flags=[]),
        config={
            "version_id": ISABELLE_VERSION_ID,
            "check_timeout_s": check_timeout_s,
            "batch_size": ISABELLE_BATCH_SIZE,
            "hol_boundary": "linear-arith fragment where HOL and the shared theories agree",
        },
        verdicts=verdicts,
        resource_stats={
            "obligations": len(verdicts),
            **{f"status_{k}": v for k, v in sorted(counts.items())},
        },
        kernel_attestations=kernel_attestations,
    )
    return result


def record_isabelle(result: IsabelleCheckResult, store: ContentStore, ledger: Ledger) -> list[str]:
    """Store produced artifacts in the CAS; append the guarantee-class entry.

    G1 (kernel attestation) when proofs exist; G0 when the run produced no
    proof (a run with zero attested proofs must not fabricate a kernel
    guarantee - R1)."""
    if result.run is None:
        raise ValueError("record_isabelle() requires an IsabelleCheckResult with a run")
    run_aid = store.put_artifact(result.run)
    refs = [run_aid]
    for obl in result.obligations:
        refs.append(store.put_artifact(obl))
    for proof in result.proofs:
        refs.append(store.put_artifact(proof))
    for diag in result.diagnostics:
        refs.append(store.put_artifact(diag.model_copy(update={"run_ref": run_aid})))
    for translation in result.translations:
        refs.append(store.put_artifact(translation))

    if not result.proofs:
        ledger.append(
            refs,
            guarantee_class="G0",
            attestation=Attestation(
                tool="isabelle-hol",
                version=PINNED_ISABELLE,
                detail="no Isabelle proofs attested; run recorded without guarantee (R1)",
            ),
        )
        return refs

    # the run-level attestation commits to every per-theorem kernel hash
    combined = sha256_hex(
        "\n".join(sorted(p.backend.kernel_hash or "" for p in result.proofs)).encode("utf-8")
    )
    ledger.append(
        refs,
        guarantee_class="G1",
        attestation=Attestation(
            tool="isabelle-hol",
            version=PINNED_ISABELLE,
            kernel_hash=combined,
            detail=(
                f"kernel-attested G1: {len(result.proofs)} proof(s) accepted by the "
                f"pinned {PINNED_ISABELLE} kernel; offline-replayable from the "
                "stored I5 payloads"
            ),
        ),
    )
    return refs
