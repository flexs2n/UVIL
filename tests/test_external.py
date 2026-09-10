"""WI-2 external-artifact corpus tests: upstream Boogie tests, end to end.

The committed `corpora/external/` set is verbatim upstream text (pinned
boogie-org/boogie commit, MIT; PROVENANCE.json) - the first externally-
authored obligations to flow through UVIL's backends (the W5 fix). These
tests pin, offline where possible:

- the provenance record and the committed file sets;
- per-file import outcomes (in-subset files import with the recorded
  obligation counts; the out-of-subset sample fails LOUD with the pinned
  I7 diagnostic kinds - measured downgrades, never silent skips);
- per-obligation z3 verdicts against expected.json (all statuses were
  observed at generation time, including refuted upstream asserts);
- the Lean twins: recorded kernel hashes recompute offline; one twin
  re-attests through the pinned kernel when Lean is installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.adapters.lean.backend import kernel_hash  # noqa: E402
from uvil.adapters.smt.backends import SmtProcessError, verdict_status  # noqa: E402
from uvil.adapters.smt.encode import OpaqueTermError  # noqa: E402
from uvil.check.core import SmtBackend  # noqa: E402
from uvil.store import obligation_identity  # noqa: E402

EXTERNAL_DIR = REPO_ROOT / "corpora" / "external"
UPSTREAM_DIR = EXTERNAL_DIR / "upstream"
OUT_SAMPLE_DIR = EXTERNAL_DIR / "upstream_out"
LEAN_DIR = EXTERNAL_DIR / "lean"
MANIFEST = json.loads((EXTERNAL_DIR / "expected.json").read_text(encoding="utf-8"))
PROVENANCE = json.loads((EXTERNAL_DIR / "PROVENANCE.json").read_text(encoding="utf-8"))
ENTRIES: dict[str, dict[str, object]] = MANIFEST["expected"]
BUDGET_MS = 2000


def _import(path: Path):
    return import_module(path.read_text(encoding="utf-8"), path.name)


def _identity(proc_name: str, fragment: str, obl) -> str:
    return obligation_identity(
        spec=obl.spec_ref,
        semantics_model=obl.semantics_model,
        program_fragment=fragment or proc_name,
        profile_version=obl.target_profile.rsplit("@", 1)[-1],
        sequent=obl.sequent,
    )


def test_provenance_pins_upstream() -> None:
    assert PROVENANCE["upstream_url"] == "https://github.com/boogie-org/boogie"
    assert len(PROVENANCE["upstream_commit"]) == 40
    assert "MIT" in PROVENANCE["license"]
    scan = PROVENANCE["scan"]
    assert scan["files_scanned"] >= 700
    assert scan["in_subset_files"] == len(list(UPSTREAM_DIR.glob("*.bpl")))
    assert scan["out_of_subset_files"] > 0  # the downgrade is measured


def test_in_subset_files_match_manifest() -> None:
    files: dict[str, dict[str, object]] = MANIFEST["files"]
    on_disk = {p.name for p in UPSTREAM_DIR.glob("*.bpl")}
    recorded = {name for name, f in files.items() if f.get("outcome") == "imported"}
    assert recorded == on_disk
    for name in sorted(on_disk):
        result = _import(UPSTREAM_DIR / name)
        assert result.ok, [d.native_message for d in result.diagnostics]
        count = sum(len(p.obligations) for p in result.procedures.values())
        assert count == files[name]["obligations"], name


def test_out_of_subset_sample_fails_loud() -> None:
    files: dict[str, dict[str, object]] = MANIFEST["files"]
    samples = {
        name: f
        for name, f in files.items()
        if f.get("outcome") != "imported" and "diagnostic_kinds" in f
    }
    on_disk = {p.name for p in OUT_SAMPLE_DIR.glob("*.bpl")}
    assert set(samples) == on_disk
    for name in sorted(on_disk):
        result = _import(OUT_SAMPLE_DIR / name)
        kinds = sorted({d.kind for d in result.diagnostics})
        assert kinds == samples[name]["diagnostic_kinds"], name
        assert not (result.ok and result.obligations), name


def _obligations_by_identity():
    """Recompute (identity -> obligation) over the in-subset files."""
    out = {}
    for path in sorted(UPSTREAM_DIR.glob("*.bpl")):
        result = _import(path)
        assert result.ok
        for proc in result.procedures.values():
            for obl in proc.obligations:
                out[_identity(proc.name, proc.program.fragment or proc.name, obl)] = obl
    return out


def test_manifest_identities_recompute() -> None:
    recomputed = _obligations_by_identity()
    assert set(recomputed) == set(ENTRIES.keys())
    assert len(recomputed) >= 50
    # obligations is the full count; identities collapse cross-file identical
    # procedures only (same fragment/spec/sequent = the same claim)
    assert MANIFEST["meta"]["obligations"] >= len(recomputed)


@pytest.mark.parametrize("obl_id", sorted(ENTRIES.keys()))
def test_external_verdict_matches_expected(obl_id: str) -> None:
    recomputed = _obligations_by_identity()
    obl = recomputed[obl_id]
    expected = ENTRIES[obl_id]["expected"]
    engine = SmtBackend("z3")
    try:
        status = verdict_status(engine.run(obl, budget=BUDGET_MS))
    except (SmtProcessError, OpaqueTermError, ValueError):
        status = "open"  # ill-sorted/unencodable external scripts stay open
    assert status == expected, ENTRIES[obl_id]["file"]


def test_lean_twin_hashes_recompute_offline() -> None:
    lean: dict[str, dict[str, object]] = MANIFEST["lean"]
    attested = {name: e for name, e in lean.items() if e["lean_status"] == "attested"}
    assert attested, "no attested twins recorded"
    for name, entry in attested.items():
        theorem = entry["theorem"]
        assert theorem is not None
        on_disk = (LEAN_DIR / name).read_text(encoding="utf-8").rstrip("\n")
        assert on_disk == theorem  # the committed twin is the recorded theorem
        assert kernel_hash(str(theorem)) == entry["kernel_hash"], name


def test_one_lean_twin_replays_through_the_pinned_kernel() -> None:
    lean: dict[str, dict[str, object]] = MANIFEST["lean"]
    attested = [e for e in lean.values() if e["lean_status"] == "attested"]
    assert attested
    from uvil.adapters.lean.backend import LeanBackend, LeanNotInstalled

    try:
        backend = LeanBackend()
    except LeanNotInstalled:  # pragma: no cover - skip-if-absent toolchain
        pytest.skip("Lean not installed")
        return
    entry = attested[0]
    verdict = backend.check_batch([str(entry["theorem"])])[0]
    assert verdict.status == "attested"
    assert verdict.file_digest == entry["kernel_hash"]
