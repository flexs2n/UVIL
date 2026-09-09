"""Isabelle benchmark slice tests: the second-ITP deliverable as tests.

- (no isabelle) manifest/disk coherence + regeneration determinism + the
  measured downgrade rate (identical structure to the Lean slice - the
  boundary policies must agree);
- (slow, isabelle) the exit criterion: SMT-discharged => HOL-attested, and
  offline replay of the recorded kernel hashes - only meaningful with the
  pinned bundle; entries generated without it carry isabelle_status=pending
  and are (re)attested here.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from uvil.adapters.isabelle.backend import (
    ISABELLE_VERSION_ID,
    IsabelleBackend,
    IsabelleNotInstalled,
    kernel_hash,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ISABELLE_CORPUS = REPO_ROOT / "corpora" / "isabelle"
EXPECTED_PATH = ISABELLE_CORPUS / "expected.json"
LEAN_MANIFEST = REPO_ROOT / "corpora" / "lean" / "expected.json"


def _isabelle_available() -> bool:
    try:
        IsabelleBackend()
        return True
    except IsabelleNotInstalled:
        return False


ISABELLE_OK = _isabelle_available()


def _manifest() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# --- manifest coherence (no isabelle required) ----------------------------------------


def test_manifest_meta_pins() -> None:
    meta = _manifest()["meta"]
    assert meta["isabelle_pin"] == "Isabelle2025"
    assert meta["version_id"] == ISABELLE_VERSION_ID
    assert meta["smt_reverified"] is True
    assert meta["families_whitelist"] == ["arith-comm", "divmod", "minmax", "abs-bound"]


def test_boundary_policies_agree_with_the_lean_slice() -> None:
    # same whitelist, same corpus, same discharge discipline: the downgrade
    # rates must be IDENTICAL (the HOL-facing boundary mirrors the Lean one)
    isabelle = _manifest()["meta"]
    lean = json.loads(LEAN_MANIFEST.read_text(encoding="utf-8"))["meta"]
    assert isabelle["families_whitelist"] == lean["families_whitelist"]
    assert isabelle["slice_entries"] == lean["slice_entries"]
    assert isabelle["downgrade_rate"] == lean["downgrade_rate"]
    assert isabelle["smt_discharged_corpus_total"] == lean["smt_discharged_corpus_total"]
    assert isabelle["downgraded_out_of_corpus"] == lean["downgraded_out_of_corpus"]


def test_slice_reaches_target_size() -> None:
    expected = _manifest()["expected"]
    rendered = [e for e in expected.values() if e["file"] is not None]
    assert len(rendered) >= 100, f"slice too small: {len(rendered)} rendered twins"


def test_every_entry_is_smt_discharged_and_honestly_labeled() -> None:
    expected = _manifest()["expected"]
    assert expected, "manifest is empty"
    for oblid, entry in expected.items():
        assert entry["smt_status"] == "discharged", oblid  # slice precondition
        assert entry["isabelle_status"] in (
            "attested",
            "failed",
            "timeout",
            "pending",
            "semantic-mismatch",
        ), oblid
        if entry["isabelle_status"] in ("attested", "pending"):
            assert entry["theorem"] is not None, oblid
            assert entry["file"] is not None, oblid
            assert (ISABELLE_CORPUS / entry["file"]).exists(), oblid
            # kernel_hash only when the bundle attested it - never fabricated
            if entry["isabelle_status"] == "pending":
                assert entry["kernel_hash"] is None, oblid
        else:
            # non-rendered entries carry NO theorem, file, or kernel hash
            assert entry["theorem"] is None, oblid
            assert entry["kernel_hash"] is None, oblid
            assert entry["file"] is None, oblid


def test_semantic_mismatches_are_the_honest_downgrades() -> None:
    # exactly the corpus entries whose terms leave the HOL boundary - the
    # same set as the Lean slice (the boundaries agree)
    expected = _manifest()["expected"]
    mismatches = sorted(
        (e["boogie_file"], e["proc"])
        for e in expected.values()
        if e["isabelle_status"] == "semantic-mismatch"
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
    on_disk = sorted(p.name for p in ISABELLE_CORPUS.glob("*.thy"))
    in_manifest = sorted(e["file"] for e in expected.values() if e["file"])
    assert on_disk == in_manifest
    for entry in expected.values():
        if entry["file"] is None:
            continue
        text = (ISABELLE_CORPUS / entry["file"]).read_text(encoding="utf-8")
        assert text == entry["theorem"] + "\n"


def test_regeneration_is_deterministic() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import gen_isabelle_slice

    entries_a, meta_a = gen_isabelle_slice.render_slice()
    entries_b, meta_b = gen_isabelle_slice.render_slice()
    assert meta_a == meta_b
    assert entries_a == entries_b  # dataclass equality incl. theorem text


# --- exit criterion + offline replay (slow, live bundle) --------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not ISABELLE_OK, reason="isabelle not installed (pin: Isabelle2025)")
def test_exit_criterion_smt_discharged_implies_hol_attested() -> None:
    backend = IsabelleBackend()
    expected = _manifest()["expected"]
    # the committed theorem lines batch into ONE theory file (startup
    # amortization); a single exit-0 build attests every twin
    theorems = [
        (ISABELLE_CORPUS / e["file"]).read_text(encoding="utf-8").strip()
        for e in expected.values()
        if e["isabelle_status"] == "pending"
    ]
    assert theorems, "no pending twins to attest"
    import tempfile
    from pathlib import Path as P

    from uvil.adapters.isabelle.encode import theory_file

    with tempfile.TemporaryDirectory(prefix="uvil-slice-") as tmp:
        workdir = P(tmp)
        (workdir / "ROOT").write_text(
            "session Uvil_Slice = HOL +\n  theories\n    Uvil_Slice_thy\n", encoding="utf-8"
        )
        (workdir / "Uvil_Slice_thy.thy").write_text(
            theory_file(theorems, "Uvil_Slice_thy"), encoding="utf-8", newline="\n"
        )
        proc = subprocess.run(
            [backend.executable, "build", "-D", ".", "Uvil_Slice"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1800,
            cwd=workdir,
        )
        assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


@pytest.mark.slow
@pytest.mark.skipif(not ISABELLE_OK, reason="isabelle not installed (pin: Isabelle2025)")
def test_offline_attestation_replay_verifies_digests() -> None:
    # only attested entries carry kernel hashes; pending entries have none to
    # verify (their hashes materialize when the bundle attests them)
    expected = _manifest()["expected"]
    for oblid, entry in expected.items():
        if entry["isabelle_status"] != "attested":
            continue
        theory = (ISABELLE_CORPUS / entry["file"]).read_text(encoding="utf-8")
        assert kernel_hash(theory) == entry["kernel_hash"], oblid
