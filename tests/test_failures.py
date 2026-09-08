"""Cross-tool failure corpus tests (M2 exit-criterion deliverable).

Required backends: z3 + boogie-parser (both always available in-repo); the
manifest must carry >=200 required-backend entries covering >=2 backends with
standardized diagnostics. The cvc5 arm re-checks the designed refutation
families through `Cvc5Backend` when UVIL_CVC5 is set (skip-if-absent).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from gen_failures import TIMEOUT_FAMILY, build_failure_programs  # noqa: E402

from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.adapters.smt.backends import (  # noqa: E402
    CVC5_ENV_VAR,
    Cvc5Backend,
    SmtVerdict,
    verdict_status,
)
from uvil.adapters.smt.encode import encode_script  # noqa: E402
from uvil.check.core import SmtBackend, check  # noqa: E402
from uvil.render import to_common_json  # noqa: E402

CORPUS = REPO_ROOT / "corpora" / "failures"
MANIFEST: dict[str, Any] = json.loads((CORPUS / "expected.json").read_text(encoding="utf-8"))
ENTRIES: dict[str, dict[str, str]] = MANIFEST["expected"]
META: dict[str, Any] = MANIFEST["meta"]

SMT_FAMILIES = {"refuted-linear", "refuted-bound", "unknown-nonlinear", TIMEOUT_FAMILY}
OPEN_FAMILIES = {"unknown-nonlinear", TIMEOUT_FAMILY}
GOLDEN_FAMILIES = [
    "refuted-linear",
    "refuted-bound",
    "unknown-nonlinear",
    "parse-if",
    "parse-call",
    "parse-uninterp",
    "parse-type",
    "parse-stray",
]
MIN_FAMILY_COUNTS = {
    "refuted-linear": 55,
    "refuted-bound": 35,
    "unknown-nonlinear": 8,
    TIMEOUT_FAMILY: 4,
    "parse-if": 15,
    "parse-call": 15,
    "parse-uninterp": 10,
    "parse-type": 15,
    "parse-stray": 10,
}


def _budget_ms(family: str) -> int:
    if family == TIMEOUT_FAMILY:
        return int(META["budget_ms_timeout"])
    if family == "unknown-nonlinear":
        return int(META["budget_ms_unknown"])
    return int(META["budget_ms_default"])


def _import(path: Path):
    return import_module(path.read_text(encoding="utf-8"), path.name)


def test_manifest_and_disk_equal() -> None:
    listed = {e["file"] for e in ENTRIES.values()}
    on_disk = {p.relative_to(CORPUS).as_posix() for p in CORPUS.rglob("*.bpl")}
    assert listed == on_disk, "manifest and disk disagree (posix paths required)"


def test_required_corpus_size_and_families() -> None:
    assert len(ENTRIES) >= 200, f"failure corpus too small: {len(ENTRIES)}"
    backends = {e["backend"] for e in ENTRIES.values()}
    assert {"z3", "boogie-parser"} <= backends  # >=2 backends, one interface
    counts: dict[str, int] = {}
    for e in ENTRIES.values():
        counts[e["family"]] = counts.get(e["family"], 0) + 1
    for family, minimum in MIN_FAMILY_COUNTS.items():
        assert counts.get(family, 0) >= minimum, f"family {family}: {counts.get(family, 0)}"


@pytest.mark.parametrize("entry_id", sorted(ENTRIES.keys()))
def test_entry_matches_expected(entry_id: str) -> None:
    entry = ENTRIES[entry_id]
    path = CORPUS / entry["file"]
    if entry["backend"] == "boogie-parser":
        result = _import(path)
        assert result.diagnostics, f"{entry_id}: designed parse failure produced no diagnostics"
        assert all(d.kind == "parse" for d in result.diagnostics)
        # verbatim-source-line invariant: every located diagnostic carries the
        # exact source line it points at
        lines = path.read_text(encoding="utf-8").splitlines()
        for d in result.diagnostics:
            if d.loc.line is not None:
                assert lines[d.loc.line - 1].strip() in d.native_message, (
                    f"{entry_id}: verbatim line missing from {d.native_message!r}"
                )
        assert entry["expected"] == "parse"
        return

    assert entry["family"] in SMT_FAMILIES
    if entry["family"] == TIMEOUT_FAMILY:
        pytest.skip("timeout family is covered by the slow-marker test")
    result = _import(path)
    assert result.ok, [d.native_message for d in result.diagnostics]
    engine = SmtBackend("z3")
    for obl in result.obligations:
        status = verdict_status(engine.run(obl, budget=_budget_ms(entry["family"])))
        if entry["family"] in OPEN_FAMILIES:
            # never-discharge invariant; the pinned backend reports budget
            # exhaustion as timeout, a plain unknown would record as "open"
            assert status in ("open", "timeout"), f"{entry_id}: {status}"
            assert status == entry["expected"]
        else:
            assert status == entry["expected"], f"{entry_id}: {status} != {entry['expected']}"


@pytest.mark.slow
def test_timeout_family_never_discharges() -> None:
    timeout_ids = sorted(k for k, v in ENTRIES.items() if v["family"] == TIMEOUT_FAMILY)
    assert timeout_ids
    engine = SmtBackend("z3")
    for entry_id in timeout_ids:
        entry = ENTRIES[entry_id]
        result = _import(CORPUS / entry["file"])
        (obl,) = result.obligations
        status = verdict_status(engine.run(obl, budget=_budget_ms(entry["family"])))
        assert status in ("timeout", "open"), f"{entry_id}: {status}"


def _first_entry(family: str) -> str:
    for entry_id in sorted(ENTRIES):
        if ENTRIES[entry_id]["family"] == family:
            return entry_id
    raise AssertionError(f"no entries for family {family}")


# --- standardized diagnostics: the M2 exit-criterion surface ------------------


@pytest.mark.parametrize("family", ["refuted-linear", "refuted-bound"])
def test_refuted_entries_produce_i6_and_i7_through_check(
    family: str, snapshot: SnapshotAssertion
) -> None:
    entry = ENTRIES[_first_entry(family)]
    imported = _import(CORPUS / entry["file"])
    result = check(imported.obligations, backend="z3", timeout_ms=_budget_ms(family))
    assert result.obligations[0].status == "refuted"
    (cex,) = result.counterexamples
    (diag,) = result.diagnostics
    assert cex.kind == "valuation"
    assert diag.kind == "unproved"
    assert cex.obligation_ref == diag.obligation_ref
    assert to_common_json(cex) == snapshot
    assert to_common_json(diag) == snapshot


@pytest.mark.parametrize("family", GOLDEN_FAMILIES)
def test_golden_standardized_i7_per_family(family: str, snapshot: SnapshotAssertion) -> None:
    entry_id = _first_entry(family)
    entry = ENTRIES[entry_id]
    if entry["backend"] == "boogie-parser":
        result = _import(CORPUS / entry["file"])
        (diag,) = result.diagnostics
    else:
        imported = _import(CORPUS / entry["file"])
        checked = check(imported.obligations, backend="z3", timeout_ms=_budget_ms(family))
        assert checked.diagnostics, entry_id
        (diag,) = checked.diagnostics
    assert to_common_json(diag) == snapshot


@pytest.mark.slow
def test_golden_timeout_i7_family(snapshot: SnapshotAssertion) -> None:
    entry = ENTRIES[_first_entry(TIMEOUT_FAMILY)]
    imported = _import(CORPUS / entry["file"])
    checked = check(imported.obligations, backend="z3", timeout_ms=_budget_ms(TIMEOUT_FAMILY))
    assert checked.diagnostics
    (diag,) = checked.diagnostics
    assert diag.kind in ("timeout", "unknown")  # never discharged either way
    assert to_common_json(diag) == snapshot


# --- cvc5 arm (skip-if-absent) ------------------------------------------------


@pytest.mark.skipif(not os.environ.get(CVC5_ENV_VAR), reason="cvc5 not configured (UVIL_CVC5)")
@pytest.mark.parametrize("family", ["refuted-linear", "refuted-bound"])
def test_cvc5_arm_agrees_on_designed_refutations(family: str) -> None:
    backend = Cvc5Backend()
    for entry_id in sorted(k for k, v in ENTRIES.items() if v["family"] == family):
        entry = ENTRIES[entry_id]
        imported = _import(CORPUS / entry["file"])
        (obl,) = imported.obligations
        verdict: SmtVerdict = backend.run(
            encode_script(obl),
            solver_ms=_budget_ms(family),
        )
        assert verdict.status == "refuted", entry_id  # by construction


# --- regeneration discipline ---------------------------------------------------


def test_regeneration_is_deterministic() -> None:
    programs_a = build_failure_programs()
    programs_b = build_failure_programs()
    assert [(p.name, p.subdir, p.source, p.family, p.backend) for p in programs_a] == [
        (p.name, p.subdir, p.source, p.family, p.backend) for p in programs_b
    ]
    # every generated program on disk is byte-identical to its deterministic source
    for program in programs_a:
        path = CORPUS / program.subdir / f"{program.name}.bpl"
        assert path.exists(), f"missing corpus file {path}"
        assert path.read_text(encoding="utf-8") == program.source, program.name


def test_entry_programs_carry_one_procedure() -> None:
    # corpus discipline: one procedure per file keeps failure attribution exact
    for entry_id, entry in sorted(ENTRIES.items()):
        imported = _import(CORPUS / entry["file"])
        assert len(imported.procedures) <= 2, entry_id  # parse-call needs the callee
        if entry["backend"] == "z3":
            assert imported.ok, entry_id
            assert len(imported.procedures) == 1
            (proc,) = imported.procedures.values()
            assert len(proc.obligations) == 1, entry_id


def test_manifest_entry_schema() -> None:
    for entry in ENTRIES.values():
        assert set(entry) == {"file", "backend", "family", "expected"}
        assert entry["backend"] in ("z3", "boogie-parser")
        assert (CORPUS / entry["file"]).exists()
