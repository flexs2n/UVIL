"""Isabelle backend + check-isabelle wiring tests.

Live-bundle tests run under the pinned Isabelle2025 and self-skip without it
(Dafny/Lean precedent). The no-upgrade invariant, the HOL boundary encoder,
the lossy-I9 downgrade emission, and record_isabelle's G0/G1 discipline are
tested without Isabelle.
"""

from __future__ import annotations

import pytest

from uvil.adapters.boogie.lower import import_module
from uvil.adapters.isabelle.backend import (
    ISABELLE_VERSION_ID,
    PINNED_ISABELLE,
    IsabelleBackend,
    IsabelleNotInstalled,
    IsabelleVerdict,
    isabelle_status,
    kernel_hash,
)
from uvil.adapters.isabelle.encode import to_hol_theorem
from uvil.check.isabelle import IsabelleCheckResult, check_isabelle, record_isabelle
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


ISABELLE_AVAILABLE = True
try:
    IsabelleBackend()
except IsabelleNotInstalled:
    ISABELLE_AVAILABLE = False


# --- no-upgrade invariant (no Isabelle needed) -------------------------------------


def test_no_code_path_upgrades_failed_or_timeout() -> None:
    for status in ("failed", "timeout"):
        verdict = IsabelleVerdict(
            status=status,  # type: ignore[arg-type]
            isabelle_version=PINNED_ISABELLE,
            theory_digest="d",
            time_ms=None,
            native_output=None,
        )
        assert isabelle_status(verdict) == "open"
    assert (
        isabelle_status(
            IsabelleVerdict(
                status="attested",
                isabelle_version=PINNED_ISABELLE,
                theory_digest="d",
                time_ms=None,
                native_output=None,
            )
        )
        == "discharged"
    )


def test_kernel_hash_commits_to_theory_bytes_and_version() -> None:
    import hashlib

    theory = 'theory T\n  imports Main\nbegin\n\ntheorem t: "(1::int) = 1" by arith\n\nend\n'
    expected = hashlib.sha256(
        theory.encode("utf-8") + ISABELLE_VERSION_ID.encode("utf-8")
    ).hexdigest()
    assert kernel_hash(theory) == expected
    assert kernel_hash(theory + "\n") != expected  # bytes-exact, not text-normalized


# --- the HOL-facing boundary (no Isabelle needed) ------------------------------------


def test_hol_encoder_agrees_with_lean_boundary() -> None:
    # the SAME whitelisted obligations encode on both ITP paths and the SAME
    # curated non-portable ones fail loud (the measured-downgrade premise)
    from uvil.adapters.lean.encode import to_lean_theorem

    (obl,) = _obligations(PROVABLE_SRC)
    hol = to_hol_theorem(obl)
    lean = to_lean_theorem(obl)
    # identical stable theorem names across the twins
    hol_name = hol.split(":")[0].removeprefix("theorem ")
    lean_name = lean.split(" :")[0].removeprefix("theorem ")
    assert hol_name == lean_name
    assert hol.endswith("by arith")
    assert "\\<And>x::int." in hol

    (real_obl,) = _obligations(
        "procedure q(x: int, r: real)\n  requires r >= 0.5\n{\n  assert x >= -1;\n}\n"
    )
    with pytest.raises(Exception, match="boundary"):
        to_hol_theorem(real_obl)

    # nonlinear (both operands symbolic): outside the boundary on both paths
    (nonlinear,) = _obligations(
        "procedure n(a: int, b: int)\n  requires a >= 0\n{\n  assert a * b < 100;\n}\n"
    )
    with pytest.raises(Exception, match="boundary"):
        to_hol_theorem(nonlinear)
    with pytest.raises(Exception, match="subset"):
        to_lean_theorem(nonlinear)


def test_hol_encoder_pins_constants_like_lean() -> None:
    # context equalities var == K propagate (the divmod corpus family)
    (obl,) = _obligations(
        "procedure d(x: int, b: int)\n  requires b == 4\n{\n  assert x div b <= x;\n}\n"
    )
    hol = to_hol_theorem(obl)
    assert "div 4" in hol


# --- backend (live bundle) ------------------------------------------------------------


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_backend_version_pin_enforced() -> None:
    backend = IsabelleBackend()
    assert backend.isabelle_version == PINNED_ISABELLE == "Isabelle2025"


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_backend_batch_attests_aligned_verdicts() -> None:
    backend = IsabelleBackend()
    (obl,) = _obligations(PROVABLE_SRC)
    theorems = [to_hol_theorem(obl), 'theorem uvil_smoke_b: "(2::int) + 2 = 4" by arith']
    verdicts = backend.check_batch(theorems)
    assert len(verdicts) == 2
    assert all(v.status == "attested" for v in verdicts)
    assert all(v.isabelle_version == PINNED_ISABELLE for v in verdicts)


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_backend_attributes_failures_exactly() -> None:
    backend = IsabelleBackend()
    good = 'theorem uvil_smoke_g: "(2::int) + 2 = 4" by arith'
    bad = 'theorem uvil_smoke_bad: "(2::int) + 2 = 5" by arith'
    verdicts = backend.check_batch([good, bad])
    assert verdicts[0].status == "attested"
    assert verdicts[1].status == "failed"
    assert verdicts[1].native_output is not None


# --- check_isabelle wiring (live bundle) ----------------------------------------------


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_check_isabelle_discharges_with_i5() -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check_isabelle([obl])
    assert result.run is not None
    assert result.run.tool.name == "isabelle-hol"
    assert result.run.tool.version == PINNED_ISABELLE
    assert result.run.verdicts[0].status == "discharged"
    assert result.obligations[0].status == "discharged"
    assert not result.diagnostics
    (proof,) = result.proofs
    assert proof.backend.name == "isabelle-hol"
    assert proof.backend.kernel_hash is not None
    assert proof.payload.format == "isabelle-theory"
    assert proof.checker.entry == "uvil-check isabelle"
    assert proof.checker.independent is True
    assert len(result.run.kernel_attestations) == 1
    assert result.run.kernel_attestations[0].checked is True


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_check_isabelle_failed_proof_stays_open_never_refuted() -> None:
    (obl,) = _obligations(REFUTABLE_SRC)
    result = check_isabelle([obl])
    assert result.obligations[0].status == "open"
    assert not result.proofs
    (diag,) = result.diagnostics
    assert diag.kind == "unproved"
    assert "never a refutation" in diag.native_message


def test_check_isabelle_semantic_mismatch_carries_lossy_i9(tmp_path) -> None:
    # the measured downgrade: I7 semantic-mismatch + I9 lossy, no fabrication.
    # Uses a fabricated verdict-free path? No - encoding happens before any
    # tool call, so this test needs no Isabelle... except the constructor.
    # We assert on the pure encoder instead when Isabelle is absent.
    (real_obl,) = _obligations(
        "procedure q(x: int, r: real)\n  requires r >= 0.5\n{\n  assert x >= -1;\n}\n"
    )
    if ISABELLE_AVAILABLE:
        result = check_isabelle([real_obl])
        assert result.obligations[0].status == "open"
        assert not result.proofs
        (diag,) = result.diagnostics
        assert diag.kind == "semantic-mismatch"
        (translation,) = result.translations
        assert translation.soundness_discipline == "lossy"
        assert translation.target_kind == "isabelle-hol-theorem"
        assert translation.residuals.dropped_fragments
    else:
        from uvil.adapters.isabelle.encode import UnsupportedTermError

        with pytest.raises(UnsupportedTermError):
            to_hol_theorem(real_obl)


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_check_isabelle_empty_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        check_isabelle([])


# --- record_isabelle (no Isabelle needed beyond fixtures) -----------------------------


def _fabricated_run():
    from uvil.artifacts import Run
    from uvil.artifacts.run import ToolDescriptor, Verdict

    return Run(
        tool=ToolDescriptor(name="isabelle-hol", version=PINNED_ISABELLE, flags=[]),
        config={},
        verdicts=[Verdict(obligation_ref="uvil:obligation@1:" + "0" * 64, status="open")],
    )


def test_record_isabelle_rejects_runless_result(tmp_path) -> None:
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError, match="run"):
        record_isabelle(IsabelleCheckResult(), store, ledger)


def test_record_isabelle_zero_proofs_appends_g0_never_fabricates_g1(tmp_path) -> None:
    result = IsabelleCheckResult()
    result.run = _fabricated_run()
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record_isabelle(result, store, ledger)
    assert refs
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G0"
    assert entry.attestation is not None
    assert "without guarantee" in (entry.attestation.detail or "")


# --- CLI: `uvil check-isabelle` ---------------------------------------------------------


def test_cli_check_isabelle_skips_when_absent(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UVIL_ISABELLE", str(tmp_path / "missing" / "isabelle"))
    runner = CliRunner()
    runner.invoke(app, ["init"])
    bpl = tmp_path / "p.bpl"
    bpl.write_text(PROVABLE_SRC, encoding="utf-8")
    result = runner.invoke(app, ["check-isabelle", str(bpl)])
    assert result.exit_code == 0, result.output
    assert "skip" in result.output


@pytest.mark.skipif(not ISABELLE_AVAILABLE, reason="isabelle not installed (pin: Isabelle2025)")
def test_cli_check_isabelle_attests(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    bpl = tmp_path / "p.bpl"
    bpl.write_text(PROVABLE_SRC, encoding="utf-8")
    result = runner.invoke(app, ["check-isabelle", str(bpl)])
    assert result.exit_code == 0, result.output
    assert "HOL-attested" in result.output
