"""Lean benchmark slice tests: the M3 exit criterion as tests.

- (no lean) manifest/disk coherence + regeneration determinism
- (slow, lean) per-entry SMT-discharged => Lean-attested (the exit criterion)
- (slow, lean) offline attestation replay: re-run the pinned kernel on the
  committed files, verify exit-0 + digest match - no UVIL code involved
- (slow, lean) G1/G2 ledger round-trip through the real record path
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from uvil.adapters.boogie.lower import import_module
from uvil.adapters.lean.backend import (
    TOOLCHAIN_ID,
    LeanBackend,
    LeanNotInstalled,
    kernel_hash,
)
from uvil.check.lean import check_lean, record_lean
from uvil.ledger import Ledger
from uvil.store import ContentStore

REPO_ROOT = Path(__file__).resolve().parent.parent
LEAN_CORPUS = REPO_ROOT / "corpora" / "lean"
EXPECTED_PATH = LEAN_CORPUS / "expected.json"

TOOLCHAIN_PIN = REPO_ROOT / "lean" / "lean-toolchain"


def _lean_available() -> bool:
    try:
        LeanBackend()
        return True
    except LeanNotInstalled:
        return False


LEAN_OK = _lean_available()


def _manifest() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# --- manifest coherence (no lean required) ------------------------------------------


def test_manifest_meta_pins() -> None:
    meta = _manifest()["meta"]
    assert meta["lean_pin"] == "4.33.1"
    assert meta["toolchain"] == TOOLCHAIN_ID
    assert meta["smt_reverified"] is True
    assert meta["families_whitelist"] == ["arith-comm", "divmod", "minmax", "abs-bound"]
    assert set(meta["families_whitelist"]) == set(meta["families_whitelist"])


def test_slice_reaches_target_size() -> None:
    expected = _manifest()["expected"]
    attested = [e for e in expected.values() if e["lean_status"] == "attested"]
    assert len(attested) >= 100, f"slice too small: {len(attested)} attested"


def test_every_entry_is_smt_discharged_and_honestly_labeled() -> None:
    expected = _manifest()["expected"]
    assert expected, "manifest is empty"
    for oblid, entry in expected.items():
        assert entry["smt_status"] == "discharged", oblid  # slice precondition
        assert entry["lean_status"] in ("attested", "unproved", "timeout", "semantic-mismatch"), (
            oblid
        )
        if entry["lean_status"] == "attested":
            assert entry["theorem"] is not None
            assert entry["kernel_hash"] is not None
            assert entry["file"] is not None
            assert (LEAN_CORPUS / entry["file"]).exists()
        else:
            # non-attested entries carry NO theorem, file, or kernel hash:
            # nothing is ever fabricated (R1)
            assert entry["theorem"] is None, oblid
            assert entry["kernel_hash"] is None, oblid
            assert entry["file"] is None, oblid


def test_semantic_mismatches_are_the_honest_downgrades() -> None:
    # these are exactly the corpus entries whose terms leave the omega subset
    expected = _manifest()["expected"]
    mismatches = sorted(
        (e["boogie_file"], e["proc"])
        for e in expected.values()
        if e["lean_status"] == "semantic-mismatch"
    )
    assert set(mismatches) == {
        ("arith_identities.bpl", "mul_comm"),  # nonlinear: a * b == b * a
        ("div_mod.bpl", "divmod_identity"),  # requires b > 0 (no constant pin)
        ("div_mod.bpl", "mod_range"),
        ("mod_reasoning.bpl", "mod_double"),
        ("negatives.bpl", "neg_mul"),  # nonlinear: (-a) * b < 0
    }


def test_committed_theorems_match_manifest() -> None:
    expected = _manifest()["expected"]
    on_disk = sorted(p.name for p in LEAN_CORPUS.glob("*.lean"))
    in_manifest = sorted(e["file"] for e in expected.values() if e["file"])
    assert on_disk == in_manifest
    for entry in expected.values():
        if entry["lean_status"] != "attested":
            continue
        text = (LEAN_CORPUS / entry["file"]).read_text(encoding="utf-8")
        assert text == entry["theorem"] + "\n"


# --- regeneration determinism (needs the pinned z3, no lean) -------------------------


def test_regeneration_is_deterministic() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import gen_lean_slice

    entries_a, meta_a = gen_lean_slice.render_slice()
    entries_b, meta_b = gen_lean_slice.render_slice()
    assert meta_a == meta_b
    assert entries_a == entries_b  # dataclass equality incl. theorem text


# --- exit criterion + offline replay (slow, live kernel) ------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not LEAN_OK, reason="lean not installed (elan absent)")
def test_exit_criterion_smt_discharged_implies_lean_attested() -> None:
    # run the pinned kernel over every committed twin; the manifest verdicts
    # must reproduce exactly
    backend = LeanBackend()
    expected = _manifest()["expected"]
    for oblid, entry in expected.items():
        if entry["lean_status"] == "semantic-mismatch":
            continue
        path = LEAN_CORPUS / entry["file"]
        proc = subprocess.run(
            [backend.executable, path.name],
            capture_output=True,
            text=True,
            check=False,
            env=backend.env(),
            timeout=120,
            cwd=path.parent,
        )
        assert proc.returncode == 0, (oblid, proc.stdout + proc.stderr)


@pytest.mark.slow
@pytest.mark.skipif(not LEAN_OK, reason="lean not installed (elan absent)")
def test_offline_attestation_replay_verifies_digests() -> None:
    # the recorded kernel_hash must be reproducible from the committed file
    # bytes alone (sha256(theorem bytes + toolchain id)) AND the kernel must
    # accept the file - no UVIL code participates in the verification
    expected = _manifest()["expected"]
    for oblid, entry in expected.items():
        if entry["lean_status"] != "attested":
            continue
        raw = (LEAN_CORPUS / entry["file"]).read_bytes()
        theorem = (
            raw[:-1] if raw.endswith(b"\n") else raw
        )  # stored payloads carry no trailing newline
        assert kernel_hash(theorem.decode("utf-8")) == entry["kernel_hash"], oblid


@pytest.mark.slow
@pytest.mark.skipif(not LEAN_OK, reason="lean not installed (elan absent)")
def test_ledger_roundtrip_g1_and_g2_from_slice(tmp_path) -> None:
    # one attested slice entry through the real check+record path: G1 without
    # faithfulness evidence, G2 with the BEq probe
    expected = _manifest()["expected"]
    (_oblid, entry) = next(
        (k, v)
        for k, v in sorted(expected.items())
        if v["lean_status"] == "attested" and v["boogie_file"].startswith("generated/")
    )
    result = import_module(
        (LEAN_CORPUS.parent / "boogie" / entry["boogie_file"]).read_text(encoding="utf-8"),
        entry["boogie_file"],
    )
    assert result.ok
    (obl,) = [
        o for p in result.procedures.values() for o in p.obligations if p.name == entry["proc"]
    ]

    checked = check_lean([obl], beq=True)
    assert checked.obligations[0].status == "discharged"
    assert len(checked.proofs) == 1
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    record_lean(checked, store, ledger)
    (g2,) = ledger.entries()
    assert g2.guarantee_class == "G2"
    assert ledger.verify() == []

    # and the no-evidence path is G1 (never silently upgraded)
    checked_plain = check_lean([obl])
    record_lean(checked_plain, store, ledger)
    entries = ledger.entries()
    assert entries[1].guarantee_class == "G1"
    assert ledger.verify() == []


def test_toolchain_pin_agrees_with_manifest() -> None:
    meta = _manifest()["meta"]
    if TOOLCHAIN_PIN.exists():
        assert TOOLCHAIN_PIN.read_text(encoding="utf-8").strip() == meta["toolchain"]
