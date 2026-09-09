"""D1 verified-translator evidence: the I9 kernel-checked artifact.

The preservation proof lives in `lean/UVIL/Core.lean` (compiled and accepted
by the pinned Lean kernel - see tests/test_translator.py). This module
records that evidence ONCE through the record_lean machinery (CAS + ledger):
the I9 `Translation` carries `soundness_discipline="kernel-checked"` and
`target_kind="lean4-core-formalization"`; the ledger attestation commits to
the exact Core.lean bytes + the pinned toolchain id, so any drift between the
recorded evidence and the file is detectable and replayable offline.

Scope guard: the translator covers the LIA subset only (see
`uvil.translate`); anything beyond is documented future work (M5+).
"""

from __future__ import annotations

from pathlib import Path

from ..adapters.lean.backend import (
    PINNED_LEAN,
    TOOLCHAIN_ID,
    LeanBackend,
    LeanNotInstalled,
)
from ..artifacts import sha256_hex
from ..artifacts.translation import Residuals, Translation
from ..ledger import Attestation, Ledger
from ..store import ContentStore

CORE_TARGET_KIND = "lean4-core-formalization"
PRESERVATION_LEMMA = "Uvil.Term.encodeLia_preserves"


def core_lean_path(core_path: Path | None = None) -> Path:
    """The Core.lean source; default = the in-repo Lake project module."""
    if core_path is not None:
        return core_path
    here = Path(__file__).resolve()
    return here.parents[3] / "lean" / "UVIL" / "Core.lean"


def translator_kernel_hash(core_text: str) -> str:
    """sha256(Core.lean bytes + toolchain id) - the recorded attestation
    (same discipline as the Lean proof files)."""
    return sha256_hex(core_text.encode("utf-8") + TOOLCHAIN_ID.encode("utf-8"))


def translator_evidence(store: ContentStore, ledger: Ledger, core_path: Path | None = None) -> str:
    """Kernel-check `lean/UVIL/Core.lean` with the pinned toolchain and record
    the D1 evidence: the I9 `Translation` (kernel-checked) + a G1 ledger
    entry committing to the exact file bytes + toolchain id.

    Raises `LeanNotInstalled` when elan is absent (skip-if-absent) and a hard
    error when the pinned kernel REJECTS the file (a failing preservation
    proof is never recorded as evidence - fail loud, R1)."""
    path = core_lean_path(core_path)
    core_text = path.read_text(encoding="utf-8")
    backend = LeanBackend()
    verdict = backend.check_batch([core_text])[0]
    if verdict.status != "attested":
        raise RuntimeError(
            "the pinned Lean kernel rejected lean/UVIL/Core.lean "
            f"({verdict.status}) - the translator preservation proof does not "
            f"compile; refusing to record evidence (fail loud, R3):\n"
            f"{verdict.native_output}"
        )

    digest = translator_kernel_hash(core_text)
    translation = Translation(
        source_artifact="uvil:core-term-ast@1:lia",
        target_artifact=f"lean:UVIL/Core.lean:{digest}",
        source_kind="obligation-term-ast",
        target_kind=CORE_TARGET_KIND,
        mapping=[
            {
                "source": "uvil.artifacts.terms.Term",
                "target": "Uvil.Term (deep embedding)",
                "translator": "Uvil.Term.encodeLia",
                "preservation": PRESERVATION_LEMMA,
            }
        ],
        soundness_discipline="kernel-checked",
        residuals=Residuals(),
        notes=(
            "D1 verified-translator evidence: for the LIA subset, "
            "interp (encodeLia t) = eval t is PROVEN in lean/UVIL/Core.lean "
            "and accepted by the pinned kernel (exit-0 compile under "
            f"{TOOLCHAIN_ID}); Python-side parity with the producing encoder "
            "is pinned by tests over the s-expression fixture format. Scope: "
            "LIA subset only (mul with a literal factor; div/mod with a "
            "positive constant divisor) - anything else is future work (M5+)."
        ),
    )
    ref = store.put_artifact(translation)
    ledger.append(
        [ref],
        guarantee_class="G1",
        attestation=Attestation(
            tool="lean4",
            version=PINNED_LEAN,
            kernel_hash=digest,
            detail=(
                "kernel-checked D1 evidence: the verified-translator "
                "preservation proof (lean/UVIL/Core.lean, "
                f"{PRESERVATION_LEMMA}) is accepted by the pinned Lean kernel; "
                "offline-replayable by compiling the committed file under the "
                "pinned toolchain"
            ),
        ),
    )
    return ref


class TranslatorNotInstalled(LeanNotInstalled):
    """Alias for skip-if-absent call sites (the translator needs elan)."""
