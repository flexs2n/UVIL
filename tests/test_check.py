from __future__ import annotations

import pytest

from tests.fixtures import make_obligation
from uvil.adapters.boogie.lower import import_module
from uvil.artifacts import Obligation, artifact_id
from uvil.check.core import CheckResult, check, record
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


def _obligations(src: str) -> list[Obligation]:
    result = import_module(src, "in.bpl")
    assert result.ok
    return list(result.obligations)


def _opaque_goal() -> Obligation:
    data = make_obligation().model_dump()
    data["sequent"]["goal"] = {"op": "opaque", "args": ["FractionalPerm", "ax-1"]}
    return Obligation.model_validate(data)


def test_check_dispatches_and_discharges() -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check([obl], backend="z3")
    assert result.run is not None
    assert result.run.tool.name == "z3"
    assert len(result.run.verdicts) == 1
    assert result.run.verdicts[0].status == "discharged"
    assert result.obligations[0].status == "discharged"
    assert not result.diagnostics
    assert not result.counterexamples


def test_check_refuted_produces_i6() -> None:
    (obl,) = _obligations(REFUTABLE_SRC)
    result = check([obl], backend="z3")
    assert result.obligations[0].status == "refuted"
    assert len(result.counterexamples) == 1
    cex = result.counterexamples[0]
    assert cex.kind == "valuation"
    assert cex.obligation_ref == artifact_id(obl)
    assert cex.shared_render.smt_lib_valuation

    # M2: a refutation is also an I7 `unproved`, paired with the I6 witness.
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.kind == "unproved"
    assert diag.obligation_ref == artifact_id(obl)
    assert "counterexample" in diag.native_message
    # deterministic text: no solver timing or session ids inside the message
    assert "ms" not in diag.native_message


def test_check_discharged_still_has_no_diagnostics() -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check([obl], backend="z3")
    assert result.obligations[0].status == "discharged"
    assert not result.diagnostics
    assert not result.counterexamples


def test_no_code_path_upgrades_unknown_or_timeout() -> None:
    # The invariant: a fabricated backend verdict of unknown/timeout can never
    # reach `discharged` through the verdict mapping.
    from uvil.adapters.smt.backends import SmtVerdict, verdict_status

    for status in ("unknown", "timeout"):
        verdict = SmtVerdict(status=status, model=None, solver_version="t", time_ms=None)
        assert verdict_status(verdict) != "discharged"


def test_check_unknown_verdict_keeps_obligation_open_with_i7() -> None:
    # z3 returns unknown for this nonlinear integer goal within a tiny budget.
    (obl,) = _obligations(
        "procedure u(x: int, y: int)\n  requires x >= 7 && y >= 7\n"
        "{\n  assert x * x * x == y * y * y + 1;\n}\n"
    )
    result = check([obl], backend="z3", timeout_ms=100)
    if result.run.verdicts[0].status in ("unknown", "timeout"):  # solver-dependent
        assert result.obligations[0].status in ("open", "timeout")
        assert result.diagnostics
        assert result.diagnostics[0].kind in ("unknown", "timeout")


def test_check_uncheckable_obligation_stays_open_with_i7() -> None:
    result = check([_opaque_goal()], backend="z3")
    assert result.obligations[0].status == "open"
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].kind == "parse"
    assert "opaque" in result.diagnostics[0].native_message
    assert result.run is not None
    assert result.run.verdicts[0].status == "open"


def test_check_empty_obligations_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        check([], backend="z3")


def test_check_unknown_backend_rejected() -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    with pytest.raises(ValueError, match="backend"):
        check([obl], backend="boogie")


def test_record_stores_artifacts_and_appends_g1(tmp_path) -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check([obl], backend="z3")
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record(result, store, ledger)

    assert refs
    for ref in refs:
        store.get_artifact(ref)  # every ref must resolve
    entries = ledger.entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.guarantee_class == "G1"
    assert entry.attestation is not None
    assert entry.attestation.tool == "z3"
    assert entry.attestation.version == "5.1.0"
    assert entry.attestation.kernel_hash is not None
    assert "no certificates" in (entry.attestation.detail or "")
    assert ledger.verify() == []


def test_record_rejects_runless_result(tmp_path) -> None:
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError, match="run"):
        record(CheckResult(), store, ledger)


def test_verdict_times_are_recorded() -> None:
    (obl,) = _obligations(PROVABLE_SRC)
    result = check([obl], backend="z3")
    assert result.run is not None
    assert result.run.verdicts[0].time_ms is not None
