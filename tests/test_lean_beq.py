"""BEq statement-equivalence probe (R4) + G2 emission tests.

The G2-withholding guard (an intentionally wrong statement yields `lossy` and
NO G2) is the key soundness test of the M3 faithfulness path.
"""

from __future__ import annotations

import pytest

from tests.fixtures import make_obligation
from uvil.adapters.boogie.lower import import_module
from uvil.adapters.lean.backend import LeanBackend, LeanNotInstalled
from uvil.adapters.lean.beq import beq_theorem_name, statement_equivalence
from uvil.adapters.lean.encode import lean_statement
from uvil.artifacts import artifact_id
from uvil.check.lean import check_lean, record_lean
from uvil.ledger import Ledger
from uvil.store import ContentStore

LEAN_AVAILABLE = True
try:
    LeanBackend()
except LeanNotInstalled:
    LEAN_AVAILABLE = False

requires_lean = pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")


PROVABLE_SRC = """
procedure p(x: int)
  requires x >= 0
{
  assert x + 0 == x;
}
"""


def _obligation() -> object:
    return make_obligation()


# --- probe outcomes (live kernel) -------------------------------------------------


@requires_lean
def test_generated_statement_is_kernel_checked() -> None:
    obl = _obligation()
    translation = statement_equivalence(obl, lean_statement(obl))
    assert translation.soundness_discipline == "kernel-checked"
    assert translation.source_kind == "obligation"
    assert translation.target_kind == "lean4-statement"
    assert translation.residuals.dropped_fragments == []
    assert translation.source_artifact == artifact_id(obl)


@requires_lean
def test_wrong_statement_is_lossy_g2_guard() -> None:
    # the key soundness guard: a subtly wrong claim (x >= 1 instead of
    # x + 1 <= cap shaped drift) must come back lossy, never kernel-checked
    obl = _obligation()
    wrong = lean_statement(obl).replace("(len + 1) ≤ cap", "(len + 2) ≤ cap")
    assert wrong != lean_statement(obl)  # the drift is real
    translation = statement_equivalence(obl, wrong)
    assert translation.soundness_discipline == "lossy"
    assert translation.residuals.dropped_fragments
    assert wrong in translation.residuals.dropped_fragments  # verbatim statement kept
    assert translation.notes is not None and "not faithful" in translation.notes


@requires_lean
def test_garbage_statement_is_lossy() -> None:
    translation = statement_equivalence(_obligation(), "theorem nonsense : False")
    assert translation.soundness_discipline == "lossy"


def test_beq_theorem_name_binds_statement_content() -> None:
    obl = _obligation()
    a = beq_theorem_name(obl, "x ≥ 0")
    b = beq_theorem_name(obl, "x ≥ 1")
    assert a != b
    assert beq_theorem_name(obl, "x ≥ 0") == a  # stable
    assert a.startswith("uvil_beq_")


@requires_lean
def test_probe_accepts_arbitrary_faithful_statement_text() -> None:
    # the interface accepts any statement text - a logically equivalent but
    # differently-phrased claim must still come back kernel-checked
    obl = _obligation()
    equivalent = "∀ (cap len : Int), (cap ≥ 0) → (len ≤ cap) → (len < cap) → (cap ≥ len + 1)"
    translation = statement_equivalence(obl, equivalent)
    assert translation.soundness_discipline == "kernel-checked"


# --- check_lean beq wiring + G2 emission (live kernel) -----------------------------


@requires_lean
def test_check_lean_beq_true_carries_kernel_checked_evidence(tmp_path) -> None:
    result = import_module(PROVABLE_SRC, "p.bpl")
    (obl,) = result.obligations
    checked = check_lean([obl], beq=True)
    assert len(checked.evidence) == 1
    (evidence,) = checked.evidence
    assert evidence.soundness_discipline == "kernel-checked"

    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record_lean(checked, store, ledger)
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G2"
    assert entry.attestation is not None
    assert "statement-equivalence" in (entry.attestation.detail or "")
    # the I9 evidence is stored and referenced by the ledger entry
    evidence_refs = [r for r in refs if r.startswith("uvil:translation@1:")]
    assert len(evidence_refs) == 1
    stored = store.get_artifact(evidence_refs[0])
    assert stored.soundness_discipline == "kernel-checked"  # type: ignore[attr-defined]
    assert entry.attestation.kernel_hash is not None


@requires_lean
def test_check_lean_beq_false_gives_g1(tmp_path) -> None:
    result = import_module(PROVABLE_SRC, "p.bpl")
    (obl,) = result.obligations
    checked = check_lean([obl])
    assert checked.evidence == []
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    record_lean(checked, store, ledger)
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G1"


@requires_lean
def test_lossy_evidence_never_upgrades_to_g2(tmp_path) -> None:
    # the guard end-to-end: a run whose ONLY faithfulness evidence is lossy
    # (fabricated here, exactly what a wrong-statement probe returns) must
    # stay G1 - G2 requires kernel-checked evidence
    from uvil.artifacts import Translation
    from uvil.artifacts.translation import Residuals

    result = import_module(PROVABLE_SRC, "p.bpl")
    (obl,) = result.obligations
    checked = check_lean([obl])
    checked.evidence.append(
        Translation(
            source_artifact=artifact_id(obl),
            target_artifact="lean4-statement:fabricated",
            source_kind="obligation",
            target_kind="lean4-statement",
            soundness_discipline="lossy",
            residuals=Residuals(dropped_fragments=["divergent statement"]),
        )
    )
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    record_lean(checked, store, ledger)
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G1"


@requires_lean
def test_check_lean_beq_skips_unattested_obligations() -> None:
    # refutable-in-SMT obligations get no proof -> no probe -> no evidence
    result = import_module("procedure r(x: int)\n{\n  assert x + x == 3 * x;\n}\n", "r.bpl")
    (obl,) = result.obligations
    checked = check_lean([obl], beq=True)
    assert not checked.proofs
    assert not checked.evidence
