from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from uvil.ledger import Attestation, Ledger

REF = "uvil:obligation@1:" + "a" * 64
REF2 = "uvil:proof@1:" + "b" * 64


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    return Ledger(tmp_path / "ledger.jsonl")


def test_append_and_verify_clean(ledger: Ledger) -> None:
    ledger.append([REF], "G1", attestation=Attestation(tool="z3", version="4.13.0"))
    ledger.append([REF2], "G0")
    assert ledger.verify() == []
    entries = ledger.entries()
    assert [e.seq for e in entries] == [1, 2]
    assert entries[1].prev_hash == entries[0].entry_hash


def test_append_rejects_bad_class(ledger: Ledger) -> None:
    with pytest.raises(ValueError, match="guarantee class"):
        ledger.append([REF], "G9")


def test_append_rejects_empty_refs(ledger: Ledger) -> None:
    with pytest.raises(ValueError, match="at least one artifact"):
        ledger.append([], "G0")


def test_tamper_with_history_detected(ledger: Ledger) -> None:
    e1 = ledger.append([REF], "G1")
    ledger.append([REF2], "G0")
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["guarantee_class"] = "G4"  # retroactive guarantee upgrade
    lines[0] = json.dumps(record)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    defects = ledger.verify()
    assert any("tampered" in d for d in defects)
    assert e1.guarantee_class == "G1"


def test_chain_break_detected(ledger: Ledger) -> None:
    ledger.append([REF], "G0")
    ledger.append([REF2], "G0")
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["prev_hash"] = None
    lines[1] = json.dumps(record)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert any("prev_hash" in d for d in ledger.verify())


def test_deleted_entry_detected(ledger: Ledger) -> None:
    ledger.append([REF], "G0")
    ledger.append([REF2], "G0")
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text(lines[1] + "\n", encoding="utf-8")
    defects = ledger.verify()
    assert any("non-monotonic" in d for d in defects)
    assert any("prev_hash" in d for d in defects)


def test_diff(ledger: Ledger) -> None:
    ledger.append([REF], "G0")
    other = Ledger(ledger.path.parent / "other.jsonl")
    other.append([REF], "G0")
    other.append([REF2], "G1")
    result = ledger.diff(other)
    assert result["only_in_self"] == []
    assert len(result["only_in_other"]) == 1


@given(st.lists(st.sampled_from(["G0", "G1", "G2", "G3", "G4"]), min_size=1, max_size=6))
@settings(deadline=None)
def test_append_monotonicity(classes: list[str]) -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        ledger = Ledger(Path(td) / "ledger.jsonl")
        for i, g in enumerate(classes):
            entry = ledger.append([f"uvil:obligation@1:{i:064x}"], g)
            assert entry.seq == i + 1
        assert ledger.verify() == []
