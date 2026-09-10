"""M5 incremental protocol tests: cache soundness, partitioning, Merkle diff.

The cache-soundness invariants under test (fail-loud, never stale-reuse):
- only `discharged` verdicts are cached;
- the cache key pins identity + backend + tool version + protocol version;
- identity change (spec/code/library churn) forces a miss;
- `incremental_since` filters reuse AND the known-set for the Merkle diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uvil.adapters.boogie.lower import import_module
from uvil.artifacts import Obligation, artifact_id
from uvil.artifacts.obligation import Sequent
from uvil.check.core import check
from uvil.ledger import Ledger
from uvil.protocol import VerdictCache, check_incremental, obligation_cache_identity
from uvil.store import ContentStore, merkle_root
from uvil.store.identity import obligation_identity

PROVABLE_SRC = """
procedure p(x: int)
  requires x >= 0
{
  assert x + 0 == x;
}
"""

REFUTABLE_SRC = """
procedure r(x: int)
{
  assert x + x == 3 * x;
}
"""


def _obligations(src: str) -> list[Obligation]:
    result = import_module(src, "in.bpl")
    assert result.ok
    return list(result.obligations)


def _workspace(tmp_path: Path) -> tuple[ContentStore, Ledger]:
    return ContentStore(tmp_path / "store"), Ledger(tmp_path / "ledger.jsonl")


# --- VerdictCache unit behavior -----------------------------------------------------


def test_cache_rejects_non_discharged(tmp_path: Path) -> None:
    cache = VerdictCache(tmp_path / "verdict-cache.json")
    with pytest.raises(ValueError, match="discharged"):
        cache.put(
            "ident",
            "z3",
            "5.1.0",
            obligation_ref="o",
            run_ref="r",
            ledger_seq=1,
            status="refuted",
        )
    assert cache.get("ident", "z3", "5.1.0") is None


def test_cache_roundtrip_and_key_pinning(tmp_path: Path) -> None:
    cache = VerdictCache(tmp_path / "verdict-cache.json")
    cache.put(
        "ident",
        "z3",
        "5.1.0",
        obligation_ref="obl:o",
        run_ref="run:r",
        ledger_seq=3,
        status="discharged",
    )
    entry = cache.get("ident", "z3", "5.1.0")
    assert entry is not None
    assert entry.status == "discharged"
    assert entry.obligation_ref == "obl:o"
    assert entry.run_ref == "run:r"
    assert entry.ledger_seq == 3

    # any pin change is a different key: no stale reuse across upgrades
    assert cache.get("ident", "cvc5", "5.1.0") is None
    assert cache.get("ident", "z3", "9.9.9") is None
    assert cache.get("other", "z3", "5.1.0") is None


def test_cache_malformed_index_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "verdict-cache.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="verdict cache"):
        VerdictCache(path).get("ident", "z3", "5.1.0")


def test_cache_known_identities_respects_incremental_since(tmp_path: Path) -> None:
    cache = VerdictCache(tmp_path / "verdict-cache.json")
    cache.put(
        "i1", "z3", "5.1.0", obligation_ref="o1", run_ref="r", ledger_seq=1, status="discharged"
    )
    cache.put(
        "i2", "z3", "5.1.0", obligation_ref="o2", run_ref="r", ledger_seq=4, status="discharged"
    )
    assert cache.known_identities() == {"i1", "i2"}
    assert cache.known_identities(4) == {"i1", "i2"}
    assert cache.known_identities(1) == {"i1"}
    assert cache.known_identities(0) == set()


# --- check_incremental --------------------------------------------------------------


def test_first_run_all_miss_then_all_hit(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    obligations = _obligations(PROVABLE_SRC)

    first = check_incremental(obligations, store, ledger, backend="z3")
    assert first.reused == []
    assert len(first.recomputed) == 1
    assert first.result.obligations[0].status == "discharged"
    assert ledger.verify() == []

    second = check_incremental(obligations, store, ledger, backend="z3")
    assert second.reused == [artifact_id(obligations[0])]
    assert second.recomputed == []
    # reused verdict: no solver call, so no timing
    assert second.result.run is not None
    (verdict,) = second.result.run.verdicts
    assert verdict.status == "discharged"
    assert verdict.time_ms is None
    assert second.result.run.config["cached"] == second.reused
    # every run is still recorded: two G1 ledger entries
    assert len(ledger.entries()) == 2


def test_identity_change_forces_miss(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    (obl,) = _obligations(PROVABLE_SRC)
    first = check_incremental([obl], store, ledger, backend="z3")
    assert first.recomputed

    # spec churn: a different spec artifact ref is a different identity. (The
    # sequent's CANONICAL form is part of the identity - ADR 0008 - but spec/
    # code/library churn all move the I2/I3 artifact refs regardless.)
    churned = obl.model_copy(
        update={
            "spec_ref": "uvil:specification@1:"
            "0000000000000000000000000000000000000000000000000000000000000000"
        }
    )
    second = check_incremental([churned], store, ledger, backend="z3")
    assert second.reused == []
    assert second.recomputed == [artifact_id(churned)]

    # the original still hits (its own cache entry is intact)
    third = check_incremental([obl], store, ledger, backend="z3")
    assert third.reused == [artifact_id(obl)]


def test_backend_pin_change_forces_miss(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    (obl,) = _obligations(PROVABLE_SRC)
    check_incremental([obl], store, ledger, backend="z3")
    cache = VerdictCache(store.root / "verdict-cache.json")
    ident = obligation_cache_identity(obl)
    # the entry is keyed under the pinned tool version only
    assert cache.get(ident, "z3", "5.1.0") is not None
    assert cache.get(ident, "z3", "OTHER-VERSION") is None


def test_only_discharged_verdicts_are_cached(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    obligations = _obligations(REFUTABLE_SRC)

    for _ in range(2):
        result = check_incremental(obligations, store, ledger, backend="z3")
        assert result.reused == []  # refuted: re-solve every time
        assert result.result.obligations[0].status == "refuted"

    cache = VerdictCache(store.root / "verdict-cache.json")
    assert cache.known_identities() == set()


def test_no_op_reorder_same_identity_hits_cache(tmp_path: Path) -> None:
    # the control group: a context reorder (formatting-only churn) keeps the
    # I2/I3 artifact refs, hence the identity, hence the cache hit
    store, ledger = _workspace(tmp_path)
    (obl,) = _obligations(PROVABLE_SRC)
    check_incremental([obl], store, ledger, backend="z3")

    reordered_ctx = list(reversed(obl.sequent.context))
    reordered = obl.model_copy(
        update={"sequent": Sequent(context=reordered_ctx, goal=obl.sequent.goal)}
    )
    result = check_incremental([reordered], store, ledger, backend="z3")
    assert result.reused == [artifact_id(reordered)]


def test_merkle_diff_stability_and_filters(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    (obl,) = _obligations(PROVABLE_SRC)
    ident = obligation_cache_identity(obl)

    first = check_incremental([obl], store, ledger, backend="z3")
    # empty known set -> empty old root, everything added
    assert first.merkle["old_root"] == merkle_root([])
    assert first.merkle["added"] == [ident]
    assert first.merkle["removed"] == []
    assert first.merkle["unchanged"] == []

    second = check_incremental([obl], store, ledger, backend="z3")
    assert second.merkle["old_root"] == second.merkle["new_root"]
    assert second.merkle["added"] == []
    assert second.merkle["removed"] == []
    assert second.merkle["unchanged"] == [ident]

    # incremental_since=0: nothing is known, so the whole set counts as added
    third = check_incremental([obl], store, ledger, backend="z3", incremental_since=0)
    assert third.reused == []
    assert third.merkle["old_root"] == merkle_root([])
    assert third.merkle["added"] == [ident]


def test_check_incremental_matches_plain_check(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    (obl,) = _obligations(PROVABLE_SRC)
    incremental = check_incremental([obl], store, ledger, backend="z3")
    plain = check([obl], backend="z3")
    assert incremental.result.run is not None
    assert plain.run is not None
    assert [v.status for v in incremental.result.run.verdicts] == [
        v.status for v in plain.run.verdicts
    ]
    assert incremental.result.obligations[0].status == plain.obligations[0].status


def test_check_incremental_rejects_bad_inputs(tmp_path: Path) -> None:
    store, ledger = _workspace(tmp_path)
    (obl,) = _obligations(PROVABLE_SRC)
    with pytest.raises(ValueError, match="at least one"):
        check_incremental([], store, ledger)
    with pytest.raises(ValueError, match="discipline"):
        check_incremental([obl], store, ledger, discipline="bogus")


def test_cache_identity_matches_m0_tuple() -> None:
    # the protocol identity IS the M0 identity over the obligation's tuple
    # plus its canonical sequent (ADR 0008: multi-VC procedures)
    (obl,) = _obligations(PROVABLE_SRC)
    assert obligation_cache_identity(obl) == obligation_identity(
        spec=obl.spec_ref,
        semantics_model=obl.semantics_model,
        program_fragment=obl.program_ref,
        profile_version=obl.target_profile.rsplit("@", 1)[-1],
        sequent=obl.sequent,
    )


# --- CLI wiring ---------------------------------------------------------------------


def test_cli_check_incremental_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    bpl = tmp_path / "in.bpl"
    bpl.write_text(PROVABLE_SRC, encoding="utf-8")

    result = runner.invoke(app, ["check", str(bpl), "--incremental"])
    assert result.exit_code == 0, result.output
    assert "0 reused / 1 recomputed" in result.output
    assert (tmp_path / ".uvil" / "verdict-cache.json").exists()

    result = runner.invoke(app, ["check", str(bpl), "--incremental"])
    assert result.exit_code == 0, result.output
    assert "1 reused / 0 recomputed" in result.output
    assert "(cached)" in result.output

    # without --incremental the default path is untouched (no cache read/write)
    cache_before = (tmp_path / ".uvil" / "verdict-cache.json").read_text(encoding="utf-8")
    result = runner.invoke(app, ["check", str(bpl)])
    assert result.exit_code == 0, result.output
    assert "(cached)" not in result.output
    cache_after = (tmp_path / ".uvil" / "verdict-cache.json").read_text(encoding="utf-8")
    assert json.loads(cache_before) == json.loads(cache_after)
