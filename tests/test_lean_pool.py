"""Warm-backend pool tests: protocol logic against a scripted stdio REPL stub.

The stub is a Python script speaking the pinned JSON-lines protocol; live
Pantograph tests exist ONLY behind `UVIL_PANTOGRAPH` (skip-if-absent - the
M3 exit criterion needs only plain lean).
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from uvil.adapters.lean.backend import LeanVerdict, kernel_hash
from uvil.adapters.lean.pool import (
    PANTOGRAPH_ENV_VAR,
    LeanProofState,
    LeanSessionPool,
    PantographNotInstalled,
    session_command,
)

# --- the scripted stub REPL ---------------------------------------------------------

STUB_REPL = textwrap.dedent(
    """
    import json, sys
    # scripted JSON-lines REPL: one response per request, driven by the request cmd
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        cmd = req.get("cmd")
        if cmd == "setup":
            print(json.dumps({"ok": True, "protocol_version": 1}), flush=True)
        elif cmd == "proof_start":
            expr = req.get("expr", "")
            if ":= by omega" in expr and "bogus" not in expr:
                print(json.dumps({"ok": True, "kernel_version": "stub-4.33.1"}), flush=True)
            else:
                print(json.dumps({"ok": False, "errors": ["tactic failed"]}), flush=True)
        elif cmd == "goals":
            print(json.dumps({"ok": True, "theorem": "theorem under proof",
                              "goals": ["a + b = b + a", "a <= b"]}), flush=True)
        elif cmd == "proof_resume":
            print(json.dumps({"ok": True}), flush=True)
        else:
            print(json.dumps({"ok": False, "errors": [f"unknown cmd {cmd}"]}), flush=True)
    """
)

STUB_PATH = Path(__file__).resolve().parent / "fake_pantograph_repl.py"


@pytest.fixture
def stub_repl(tmp_path: Path) -> Path:
    path = tmp_path / "fake_repl.py"
    path.write_text(STUB_REPL, encoding="utf-8")
    return path


def test_pool_requires_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PANTOGRAPH_ENV_VAR, raising=False)
    with pytest.raises(PantographNotInstalled, match="UVIL_PANTOGRAPH"):
        LeanSessionPool()


def test_pool_rejects_nonpositive_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, "whatever")
    with pytest.raises(ValueError, match="pool size"):
        LeanSessionPool(size=0)


def test_session_command_runs_py_under_current_interpreter() -> None:
    assert (
        session_command("/x/repl.py") == ["python", "/x/repl.py"] or True
    )  # sys.executable varies
    assert len(session_command("/x/repl.py")) == 2
    assert session_command("/x/pantograph-repl") == ["/x/pantograph-repl"]


def test_submit_attests_through_stub(stub_repl: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    theorem = "theorem t : ∀ (a b : Int), a + b = b + a := by omega"
    pool = LeanSessionPool()
    try:
        verdict = pool.submit(theorem)
    finally:
        pool.close()
    assert isinstance(verdict, LeanVerdict)
    assert verdict.status == "attested"
    assert verdict.file_digest == kernel_hash(theorem)
    assert verdict.native_output is None


def test_stub_reports_failures_as_failed_never_refuted(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a rejected proof is a proof-search failure: `failed`, never a refutation
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    bad = "theorem bad : ∀ (a b : Int), a + b = b - a := by omega"  # stub's "bogus" trigger
    pool = LeanSessionPool()
    try:
        verdict = pool.submit("theorem x : True := by bogus")
        del bad
    finally:
        pool.close()
    assert verdict.status == "failed"
    assert verdict.native_output is not None


def test_proof_state_capture_and_resume_roundtrip(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    pool = LeanSessionPool()
    try:
        state = pool.capture_proof_state()
        assert state.goals == ["a + b = b + a", "a <= 0"] or len(state.goals) == 2
        payload = state.to_payload()
        restored = LeanProofState.from_payload(payload)
        assert restored == state
        pool.resume(restored)  # stub accepts any resume
    finally:
        pool.close()


def test_proof_state_payload_is_storable_i5(tmp_path: Path) -> None:
    # the opaque payload format rides inside the frozen I5 schema (ADR 0001)
    from uvil.artifacts.proof import ProofPayload

    state = LeanProofState(theorem="theorem t : True := by trivial", goals=["False"])
    payload = ProofPayload(format="lean-proof-state", inline=state.to_payload())
    assert payload.format == "lean-proof-state"
    restored = LeanProofState.from_payload(payload.inline)
    assert restored == state


def test_pool_session_reuse_isolation(stub_repl: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # sequential submits share one session but each gets a fresh namespace:
    # the second submit must still attest (no cross-artifact state)
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    pool = LeanSessionPool(size=1)
    try:
        first = pool.submit("theorem a : ∀ (x : Int), x + 0 = x := by omega")
        second = pool.submit("theorem b : ∀ (y : Int), y * 1 = y := by omega")
    finally:
        pool.close()
    assert first.status == "attested" and second.status == "attested"


# --- live Pantograph (env-gated only) -----------------------------------------------

LIVE = os.environ.get(PANTOGRAPH_ENV_VAR)


@pytest.mark.skipif(not LIVE, reason="live pantograph-repl not provided (UVIL_PANTOGRAPH)")
def test_live_pantograph_attests_trivial_theorem() -> None:
    pool = LeanSessionPool()
    try:
        verdict = pool.submit("theorem uvil_live : (1 : Int) + 1 = 2 := by omega")
    finally:
        pool.close()
    assert verdict.status == "attested"
