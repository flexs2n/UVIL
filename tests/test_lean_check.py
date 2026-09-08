"""Lean backend + check-lean wiring tests.

Live-kernel tests run under the pinned toolchain and self-skip without elan
(the whole `test_lean_*` module pair follows the Dafny precedent). The
no-upgrade invariant and record_lean guarantee-class discipline are tested
without Lean where possible.
"""

from __future__ import annotations

import pytest

from tests.fixtures import make_obligation
from uvil.adapters.boogie.lower import import_module
from uvil.adapters.lean.backend import (
    PINNED_LEAN,
    TOOLCHAIN_ID,
    LeanBackend,
    LeanNotInstalled,
    LeanVerdict,
    kernel_hash,
    lean_status,
    proof_file_bytes,
)
from uvil.adapters.lean.encode import to_lean_theorem
from uvil.check.lean import LeanCheckResult, check_lean, record_lean
from uvil.ledger import Ledger
from uvil.store import ContentStore

REFUTABLE_SRC = """
procedure r(x: int)
{
  assert x + x == 3 * x;
}
"""

PROVABLE_SRC = """
procedure p(x: int)
  requires x >= 0
{
  assert x + 0 == x;
}
"""


def _obligations(src: str) -> list[object]:
    result = import_module(src, "in.bpl")
    assert result.ok, [d.native_message for d in result.diagnostics]
    return list(result.obligations)


LEAN_AVAILABLE = True
try:
    LeanBackend()
except LeanNotInstalled:
    LEAN_AVAILABLE = False


# --- no-upgrade invariant (no Lean needed) ---------------------------------------


def test_no_code_path_upgrades_failed_or_timeout() -> None:
    # the invariant: a fabricated backend verdict of failed/timeout can never
    # reach `discharged` through the verdict mapping - and nothing via Lean
    # is ever `refuted` (proof-search failure produces no counterexample)
    for status in ("failed", "timeout"):
        verdict = LeanVerdict(
            status=status, kernel_version="t", file_digest="d", time_ms=None, native_output=None
        )
        assert lean_status(verdict) == "open"
    assert (
        lean_status(
            LeanVerdict(
                status="attested",
                kernel_version="t",
                file_digest="d",
                time_ms=None,
                native_output=None,
            )
        )
        == "discharged"
    )


def test_kernel_hash_commits_to_file_bytes_and_toolchain() -> None:
    import hashlib

    theorem = "theorem t : (1 : Int) + 1 = 2 := by omega"
    expected = hashlib.sha256(proof_file_bytes(theorem) + TOOLCHAIN_ID.encode("utf-8")).hexdigest()
    assert kernel_hash(theorem) == expected
    assert kernel_hash(theorem + "\n") != expected  # bytes-exact, not text-normalized


# --- backend (live kernel) --------------------------------------------------------


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_backend_version_pin_enforced() -> None:
    backend = LeanBackend()
    assert backend.kernel_version == PINNED_LEAN == "4.33.1"


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_backend_batch_attests_aligned_verdicts() -> None:
    backend = LeanBackend()
    theorems = [
        to_lean_theorem(make_obligation()),
        "theorem uvil_smoke_b : ∀ (a b : Int), a + b = b + a := by omega",
    ]
    verdicts = backend.check_batch(theorems)
    assert len(verdicts) == 2
    assert all(v.status == "attested" for v in verdicts)
    assert all(v.kernel_version == PINNED_LEAN for v in verdicts)
    assert all(v.file_digest == kernel_hash(t) for v, t in zip(verdicts, theorems, strict=True))


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_backend_attributes_failures_exactly() -> None:
    backend = LeanBackend()
    good = "theorem uvil_smoke_g : ∀ (a b : Int), a + b = b + a := by omega"
    bad = "theorem uvil_smoke_bad : ∀ (a b : Int), a + b = b - a := by omega"
    verdicts = backend.check_batch([good, bad])
    assert verdicts[0].status == "attested"
    assert verdicts[1].status == "failed"
    assert verdicts[1].native_output is not None
    assert "omega" in verdicts[1].native_output


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_backend_timeout_never_attests() -> None:
    backend = LeanBackend(check_timeout_s=1.0)
    verdicts = backend.check_batch(["theorem uvil_smoke_ok : (1 : Int) = 1 := by omega"])
    assert verdicts[0].status in ("attested", "timeout")
    assert verdicts[0].status != "failed"  # a 1s budget suffices for omega here


# --- check_lean wiring (live kernel) ----------------------------------------------


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_check_lean_discharges_with_i5() -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check_lean([obl])
    assert result.run is not None
    assert result.run.tool.name == "lean4"
    assert result.run.tool.version == PINNED_LEAN
    assert result.run.config["toolchain"] == TOOLCHAIN_ID
    assert result.run.verdicts[0].status == "discharged"
    assert result.obligations[0].status == "discharged"
    assert not result.diagnostics
    (proof,) = result.proofs
    assert proof.obligation_ref == result.run.verdicts[0].obligation_ref
    assert proof.backend.name == "lean4"
    assert proof.backend.version == PINNED_LEAN
    assert proof.backend.kernel_hash is not None
    assert proof.payload.format == "lean-proof-term"
    assert proof.payload.inline is not None
    assert proof.checker.entry == "uvil-check lean4"
    assert proof.checker.independent is True
    # R1: every attested obligation's kernel attestation is recorded on the run
    assert len(result.run.kernel_attestations) == 1
    assert result.run.kernel_attestations[0].checked is True


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_check_lean_failed_proof_stays_open_never_refuted() -> None:
    # a provably FALSE assertion: SMT refutes it, Lean proof search cannot
    # discharge it - and Lean has no counterexample to offer, so it must stay
    # open with an I7 unproved, never refuted (R1)
    (obl,) = _obligations(REFUTABLE_SRC)
    result = check_lean([obl])
    assert result.obligations[0].status == "open"
    assert result.run.verdicts[0].status == "open"
    assert not result.proofs
    kinds = [d.kind for d in result.diagnostics]
    assert kinds == ["unproved"]
    assert "never a refutation" in result.diagnostics[0].native_message


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_check_lean_semantic_mismatch_stays_open() -> None:
    (obl,) = _obligations(
        "procedure q(x: int, r: real)\n  requires r >= 0.5\n{\n  assert x >= -1;\n}\n"
    )
    result = check_lean([obl])
    assert result.obligations[0].status == "open"
    (diag,) = result.diagnostics
    assert diag.kind == "semantic-mismatch"
    assert "omega" in diag.native_message


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_check_lean_mixed_batch() -> None:
    provable = _obligations(PROVABLE_SRC)[0]
    refutable = _obligations(REFUTABLE_SRC)[0]
    real = _obligations(
        "procedure q(x: int, r: real)\n  requires r >= 0.5\n{\n  assert x >= -1;\n}\n"
    )[0]
    result = check_lean([provable, refutable, real])
    assert [o.status for o in result.obligations] == ["discharged", "open", "open"]
    assert len(result.proofs) == 1
    assert [d.kind for d in result.diagnostics] == ["unproved", "semantic-mismatch"]
    assert result.run is not None and len(result.run.verdicts) == 3


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_check_lean_empty_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        check_lean([])


# --- CLI: `uvil check-lean` + `uvil attest` ----------------------------------------


def _proof_refs(store: ContentStore) -> list[str]:
    """Enumerate stored proof-artifact refs by walking the CAS objects."""
    refs = []
    for obj in sorted(store.objects.glob("*/*")):
        try:
            store.get_artifact(f"uvil:proof@1:{obj.name}")
        except Exception:
            continue
        refs.append(f"uvil:proof@1:{obj.name}")
    return refs


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_cli_check_lean_then_attest_replays_offline(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    bpl = tmp_path / "p.bpl"
    bpl.write_text(PROVABLE_SRC, encoding="utf-8")

    result = runner.invoke(app, ["check-lean", str(bpl)])
    assert result.exit_code == 0, result.output
    assert "kernel-attested" in result.output

    store = ContentStore(tmp_path / ".uvil")
    (proof_ref,) = _proof_refs(store)
    proof = store.get_artifact(proof_ref)
    assert proof.checker.entry == "uvil-check lean4"  # type: ignore[attr-defined]

    result = runner.invoke(app, ["attest", proof_ref, "--state", str(tmp_path / ".uvil")])
    assert result.exit_code == 0, result.output
    assert "attestation verified" in result.output

    # tampering with the payload must be detected by the recorded hash
    tampered = proof.model_copy(
        update={
            "payload": proof.payload.model_copy(  # type: ignore[attr-defined]
                update={"inline": proof.payload.inline + "\ntheorem bogus : False := by trivial"}  # type: ignore[attr-defined]
            )
        }
    )
    tampered_ref = store.put_artifact(tampered)
    result = runner.invoke(app, ["attest", tampered_ref, "--state", str(tmp_path / ".uvil")])
    assert result.exit_code == 1
    assert "kernel hash match" in result.output


# --- record_lean (no Lean needed beyond fixtures) ---------------------------------


def test_record_lean_rejects_runless_result(tmp_path) -> None:
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError, match="run"):
        record_lean(LeanCheckResult(), store, ledger)


def test_record_lean_zero_proofs_appends_g0_never_fabricates_g1(tmp_path) -> None:
    # a run with no attested proofs must not fabricate a kernel guarantee (R1)
    result = LeanCheckResult()
    result.run = _fabricated_run()
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record_lean(result, store, ledger)
    assert refs
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G0"
    assert entry.attestation is not None
    assert "without guarantee" in (entry.attestation.detail or "")


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_record_lean_attested_appends_g1(tmp_path) -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check_lean([obl])
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record_lean(result, store, ledger)

    for ref in refs:
        store.get_artifact(ref)  # every ref must resolve
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G1"
    assert entry.attestation is not None
    assert entry.attestation.tool == "lean4"
    assert entry.attestation.version == PINNED_LEAN
    assert entry.attestation.kernel_hash is not None
    assert "kernel-attested" in (entry.attestation.detail or "")
    assert ledger.verify() == []
    # the I5 stored under its ref round-trips and its kernel hash resolves
    proofs = [store.get_artifact(ref) for ref in refs if ref.startswith("uvil:proof@1:")]
    assert len(proofs) == 1
    assert proofs[0].backend.kernel_hash  # type: ignore[attr-defined]


def _fabricated_run():
    from uvil.artifacts import Run
    from uvil.artifacts.run import ToolDescriptor, Verdict

    return Run(
        tool=ToolDescriptor(name="lean4", version=PINNED_LEAN, flags=[]),
        config={},
        verdicts=[Verdict(obligation_ref="uvil:obligation@1:" + "0" * 64, status="open")],
    )
