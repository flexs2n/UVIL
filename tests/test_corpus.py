from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from gen_corpus import CURATED, build_generated_programs, identities_for  # noqa: E402

from tests.fixtures import make_obligation  # noqa: E402
from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.adapters.smt.backends import verdict_status  # noqa: E402
from uvil.check.core import SmtBackend  # noqa: E402
from uvil.store import obligation_identity  # noqa: E402

CORPUS_DIR = REPO_ROOT / "corpora" / "boogie"
EXPECTED: dict[str, Any] = json.loads((CORPUS_DIR / "expected.json").read_text(encoding="utf-8"))
ENTRIES: dict[str, dict[str, str]] = EXPECTED["expected"]
SLOW_FAMILIES = {"timeout"}


def _import_file(path: Path):
    result = import_module(path.read_text(encoding="utf-8"), path.name)
    assert result.ok, [d.native_message for d in result.diagnostics]
    return result


def _budget_ms(entry: dict[str, str]) -> int:
    meta = EXPECTED["meta"]
    if entry["family"] == "timeout":
        return int(meta["budget_ms_timeout"])
    return int(meta["budget_ms_default"])


def test_corpus_manifest_and_files_exist() -> None:
    assert len(ENTRIES) >= 500, f"corpus too small: {len(ENTRIES)}"
    listed_files = {e["file"] for e in ENTRIES.values()}
    on_disk = {p.relative_to(CORPUS_DIR).as_posix() for p in CORPUS_DIR.rglob("*.bpl")}
    assert listed_files == on_disk


def test_curated_files_all_in_manifest() -> None:
    on_disk = {p.name for p in CORPUS_DIR.glob("*.bpl")}
    assert set(CURATED) == on_disk


@pytest.mark.parametrize("obl_id", sorted(ENTRIES.keys()))
def test_corpus_verdict_matches_expected(obl_id: str) -> None:
    entry = ENTRIES[obl_id]
    if entry["family"] in SLOW_FAMILIES:
        pytest.skip("timeout family is covered by the slow-marker test")
    path = CORPUS_DIR / entry["file"]
    result = _import_file(path)
    ids = {i: name for i, name in identities_for(result).items()}
    assert obl_id in ids, f"identity {obl_id} not found in {path.name}"
    proc_name = ids[obl_id]
    proc = result.procedures[proc_name]
    # a loop procedure emits several WP obligations; the identity pins the sequent
    matches = [
        o
        for o in proc.obligations
        if obligation_identity(
            spec=o.spec_ref,
            semantics_model=o.semantics_model,
            program_fragment=proc.program.fragment or proc.name,
            profile_version=o.target_profile.rsplit("@", 1)[-1],
            sequent=o.sequent,
        )
        == obl_id
    ]
    (obl,) = matches
    engine = SmtBackend("z3")
    status = verdict_status(engine.run(obl, budget=_budget_ms(entry)))
    assert status == entry["expected"], f"{entry['file']}/{entry['proc']}"


@pytest.mark.slow
def test_timeout_family_never_discharges() -> None:
    timeout_ids = [k for k, v in ENTRIES.items() if v["family"] == "timeout"]
    assert timeout_ids
    for obl_id in timeout_ids:
        entry = ENTRIES[obl_id]
        result = _import_file(CORPUS_DIR / entry["file"])
        matches = [
            o
            for o in result.obligations
            if obligation_identity(
                spec=o.spec_ref,
                semantics_model=o.semantics_model,
                program_fragment=o.program_ref,
                profile_version=o.target_profile.rsplit("@", 1)[-1],
                sequent=o.sequent,
            )
            == obl_id
        ]
        (obl,) = matches
        engine = SmtBackend("z3")
        status = verdict_status(engine.run(obl, budget=_budget_ms(entry)))
        assert status in ("timeout", "open"), f"{entry['file']}: {status}"


def test_corpus_regeneration_is_deterministic() -> None:
    """Same seed => same programs => same identity set."""
    sources_a = [(p.name, p.source) for p in build_generated_programs()]
    sources_b = [(p.name, p.source) for p in build_generated_programs()]
    assert sources_a == sources_b

    def ids(sources):
        out = set()
        for _, src in sources:
            result = import_module(src, "regen.bpl")
            assert result.ok
            out |= set(identities_for(result))
        return out

    ids_a, ids_b = ids(sources_a), ids(sources_b)
    assert ids_a == ids_b
    assert len(ids_a) >= 450  # literal collisions may merge a few programs


def test_identity_function_is_stable() -> None:
    kwargs = {
        "spec": "s",
        "semantics_model": "m",
        "program_fragment": "f",
        "profile_version": "1",
        "sequent": make_obligation().sequent,
    }
    a = obligation_identity(**kwargs)
    b = obligation_identity(**kwargs)
    assert a == b
