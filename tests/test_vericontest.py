"""VeriContest harvest tests (M6, ADR 0009): the backend-invariance slice.

- (no verus needed) manifest/provenance coherence + the measured downgrade
  rate + offline import replay over the committed bytes;
- the comparison protocol: native Verus run records vs UVIL z3 verdicts on
  the in-subset generated harnesses (the upstream in-subset set is EMPTY -
  all 1007 tasks are out of the scalar-contract subset, measured at fetch
  time; the honest headline is the downgrade rate).
"""

from __future__ import annotations

import json
from pathlib import Path

from uvil.adapters.verus.importer import import_verus

REPO_ROOT = Path(__file__).resolve().parent.parent
VERICONTEST_DIR = REPO_ROOT / "corpora" / "vericontest"
UPSTREAM_DIR = VERICONTEST_DIR / "upstream"
GENERATED_DIR = VERICONTEST_DIR / "generated"
EXPECTED_PATH = VERICONTEST_DIR / "expected.json"
PROVENANCE_PATH = VERICONTEST_DIR / "PROVENANCE.json"


def _manifest() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def _provenance() -> dict:
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


# --- manifest coherence (no verus required) --------------------------------------------


def test_manifest_meta_pins() -> None:
    meta = _manifest()["meta"]
    assert meta["verus_tag"].startswith("release/")
    assert meta["verus_commit"] == "8dea4a2196ebf99449fe2f141a2fb30acae3f17c"
    assert meta["verus_toolchain"] == "1.98.0-x86_64-pc-windows-msvc"
    assert meta["z3_pin"] == "5.1.0"


def test_provenance_pins_the_fetch() -> None:
    prov = _provenance()
    assert prov["upstream_url"] == "https://github.com/HIPREL-Group/VeriContest"
    assert prov["upstream_commit"] == "b9657edf33b68dbd4992b501967730b30883a04e"
    assert "CC BY 4.0" in prov["license"]
    assert prov["sample"]["sampled"] == 100
    assert prov["sample"]["selection_rule"].startswith("first 100 task dirs")


def test_sample_size_and_provenance_agree() -> None:
    expected = _manifest()["expected"]
    upstream = [k for k, e in expected.items() if e["family"] == "upstream"]
    generated = [k for k, e in expected.items() if e["family"] == "generated"]
    assert len(upstream) == 100
    assert len(generated) == 6
    on_disk = sorted(d.name for d in UPSTREAM_DIR.iterdir() if d.is_dir())
    assert on_disk == sorted(k.split("/", 1)[1] for k in upstream)


def test_upstream_downgrade_rate_is_the_honest_headline() -> None:
    meta = _manifest()["meta"]
    expected = _manifest()["expected"]
    upstream = [e for e in expected.values() if e["family"] == "upstream"]
    downgraded = [e for e in upstream if e["import_kind"] != "procedures"]
    assert meta["sample_size"] == len(upstream)
    assert meta["upstream_downgraded"] == len(downgraded)
    assert meta["upstream_downgrade_rate"] == round(len(downgraded) / len(upstream), 4)
    # every upstream downgrade carries its I7 kind (fail loud, verbatim fragments)
    assert all(e["import_detail"] in ("semantic-mismatch", "parse") for e in downgraded)


def test_native_ground_truth_records_run_details() -> None:
    expected = _manifest()["expected"]
    for task, entry in expected.items():
        assert entry["native_status"] in ("verified", "failed", "unsupported-locally"), task
        assert entry["native_exit_code"] is not None, task
        # a results line exists whenever verification actually ran; an
        # unsupported-locally task (language pre-check error, no results
        # summary) is recorded with its exit code alone
        if entry["native_status"] == "unsupported-locally":
            continue
        assert entry["native_results_line"] is not None, task
        assert entry["native_results_line"].startswith("verification results::"), task
    # the generated arm: 4 safe + 2 refutable, exit codes 0 / non-0
    gen = {k: e for k, e in expected.items() if e["family"] == "generated"}
    verified = [k for k, e in gen.items() if e["native_status"] == "verified"]
    failed = [k for k, e in gen.items() if e["native_status"] == "failed"]
    assert len(verified) == 4
    assert len(failed) == 2
    assert all(gen[k]["native_exit_code"] == 0 for k in verified)
    assert all(gen[k]["native_exit_code"] != 0 for k in failed)


def test_in_subset_agreement_metric() -> None:
    meta = _manifest()["meta"]
    expected = _manifest()["expected"]
    gen = [e for e in expected.values() if e["family"] == "generated"]
    # native verdict and UVIL z3 verdict AGREE on every in-subset harness -
    # discharged (safe) / refuted (refutable); a disagreement would be a
    # finding recorded in meta.disagreements, never papered over
    assert all(e["agreement"] == "agree" for e in gen), [
        (k, e["agreement"])
        for k, e in _manifest()["expected"].items()
        if e["family"] == "generated"
    ]
    assert meta["disagreements"] == []
    assert meta["in_subset_agreement"] == f"{len(gen)}/{len(gen)}"
    for e in gen:
        if e["native_status"] == "verified":
            assert e["z3_status"] == "discharged"
        else:
            assert e["z3_status"] == "refuted"


# --- offline import replay over the committed bytes -------------------------------------


def test_import_replay_reproduces_the_manifest() -> None:
    expected = _manifest()["expected"]
    # upstream: the diagnostic kind replays offline from the committed bytes
    for name, entry in expected.items():
        if entry["family"] != "upstream":
            continue
        task = UPSTREAM_DIR / name.split("/", 1)[1]
        source = (task / "verified.rs").read_text(encoding="utf-8", errors="replace")
        result = import_verus(source, f"{task.name}.rs")
        if entry["import_kind"] == "diagnostic":
            assert not result.procedures or result.diagnostics, name
            assert result.diagnostics[0].kind == entry["import_detail"], name
        else:
            assert result.ok and result.procedures, name
    # generated: the committed harnesses import cleanly and yield obligations
    for name, entry in expected.items():
        if entry["family"] != "generated":
            continue
        source = (GENERATED_DIR / f"{name.split('/', 1)[1]}.rs").read_text(encoding="utf-8")
        result = import_verus(source, f"{name.split('/', 1)[1]}.rs")
        assert result.ok, name
        (proc,) = result.procedures.values()
        assert str(len(proc.obligations)) == entry["import_detail"], name


def test_generated_harnesses_are_in_subset_and_deterministic() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import gen_vericontest_slice

    for name, spec in gen_vericontest_slice.HARNESSES.items():
        text = (GENERATED_DIR / f"{name}.rs").read_text(encoding="utf-8")
        assert text == gen_vericontest_slice._render_harness(name, spec), name
