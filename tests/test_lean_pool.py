"""Warm-backend pool tests: protocol v2 logic against a scripted stdio REPL stub.

The stub is a Python script speaking the pinned protocol v2 (`goal.*` over
`{"cmd", "payload"}` lines, with the `ready.` banner); live Pantograph tests
exist ONLY behind `UVIL_PANTOGRAPH` (skip-if-absent - the M3 exit criterion
needs only plain lean). The live-arm discovery findings (banner, payload
form, `goal.start` term parsing, sorry gate) are pinned against the real
binary in `tests/test_lean_discovery.py`.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from uvil.adapters.lean.backend import TOOLCHAIN_ID, LeanVerdict, kernel_hash
from uvil.adapters.lean.pool import (
    PANTOGRAPH_ENV_VAR,
    LeanProofState,
    LeanSessionPool,
    PantographNotInstalled,
    PantographSession,
    session_command,
    split_theorem,
)

# --- the scripted stub REPL (protocol v2) -------------------------------------------

STUB_REPL = textwrap.dedent(
    """
    import json, sys
    # scripted v2 REPL: banner, then one response per request
    print("ready.", flush=True)
    next_state = 0
    opened = {}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        cmd = req.get("cmd")
        payload = req.get("payload") or {}
        if cmd == "stat":
            print(json.dumps({"nGoals": 0}), flush=True)
        elif cmd == "goal.start":
            expr = payload.get("expr", "")
            next_state += 1
            opened[next_state] = expr
            print(json.dumps({"stateId": next_state, "root": "_uniq.stub"}), flush=True)
        elif cmd == "goal.tactic":
            sid = payload.get("stateId")
            tactic = payload.get("tactic", "")
            if sid not in opened:
                print(json.dumps(
                    {"desc": f"Invalid state index {sid}", "error": "index"}), flush=True)
            elif tactic == "sorry":
                print(json.dumps({"goals": [], "hasSorry": True, "hasUnsafe": False,
                                  "messages": [], "nextStateId": sid + 1000}), flush=True)
            elif "failing" in opened[sid] or tactic == "bogus":
                print(json.dumps({"hasSorry": False, "hasUnsafe": False, "messages": [
                    {"severity": "error", "data": "tactic failed"}]}), flush=True)
            else:
                print(json.dumps({"goals": [], "hasSorry": False, "hasUnsafe": False,
                                  "messages": [], "nextStateId": sid + 1000}), flush=True)
        elif cmd == "goal.print":
            sid = payload.get("stateId")
            if sid not in opened:
                print(json.dumps(
                    {"desc": f"Invalid state index {sid}", "error": "index"}), flush=True)
            else:
                print(json.dumps({"goals": [{"target": {"pp": opened[sid]}}],
                                  "rootHasSorry": False, "rootHasUnsafe": False}), flush=True)
        else:
            print(json.dumps({"desc": f"unknown cmd {cmd}", "error": "command"}), flush=True)
    """
)

STUB_PATH = Path(__file__).resolve().parent / "fake_pantograph_repl.py"

GOOD_THEOREM = "theorem t : ∀ (a b : Int), a + b = b + a := by omega"
FAILING_THEOREM = "theorem t : ∀ (a b : Int), a + b = b - a := by omega"


@pytest.fixture
def stub_repl(tmp_path: Path) -> Path:
    path = tmp_path / "fake_repl.py"
    path.write_text(STUB_REPL, encoding="utf-8")
    return path


# --- protocol v2 units ----------------------------------------------------------------


def test_split_theorem_generated_shape() -> None:
    stmt, body = split_theorem(GOOD_THEOREM)
    assert stmt == "∀ (a b : Int), a + b = b + a"
    assert body == "omega"


def test_split_theorem_rejects_malformed() -> None:
    with pytest.raises(ValueError, match="shape"):
        split_theorem("theorem t : True")
    with pytest.raises(ValueError, match="shape"):
        split_theorem("lemma t : True := by trivial")
    with pytest.raises(ValueError, match="single-tactic"):
        split_theorem("theorem t : True := by\n  trivial\n  trivial")


def test_session_command_launches_with_init_import() -> None:
    assert session_command("/x/repl.py")[-1] == "Init"
    assert session_command("/x/pantograph-repl") == ["/x/pantograph-repl", "Init"]
    assert len(session_command("/x/repl.py")) == 3


def test_pool_requires_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PANTOGRAPH_ENV_VAR, raising=False)
    with pytest.raises(PantographNotInstalled, match="UVIL_PANTOGRAPH"):
        LeanSessionPool()


def test_pool_rejects_nonpositive_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, "whatever")
    with pytest.raises(ValueError, match="pool size"):
        LeanSessionPool(size=0)


def test_submit_attests_through_stub(stub_repl: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    pool = LeanSessionPool()
    try:
        verdict = pool.submit(GOOD_THEOREM)
    finally:
        pool.close()
    assert isinstance(verdict, LeanVerdict)
    assert verdict.status == "attested"
    assert verdict.file_digest == kernel_hash(GOOD_THEOREM)
    assert verdict.kernel_version == TOOLCHAIN_ID
    assert verdict.native_output is None


def test_stub_reports_failures_as_failed_never_refuted(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a rejected proof is a proof-search failure: `failed`, never a refutation
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    pool = LeanSessionPool()
    try:
        verdict = pool.submit("theorem x : True := by bogus")
    finally:
        pool.close()
    assert verdict.status == "failed"
    assert verdict.native_output is not None


def test_sorry_tainted_proof_is_failed_never_attested(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sorry_theorem = "theorem t : ∀ (a : Int), a * 2 = a + a := by sorry"
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    pool = LeanSessionPool()
    try:
        verdict = pool.submit(sorry_theorem)
    finally:
        pool.close()
    assert verdict.status == "failed"
    assert "sorry" in (verdict.native_output or "")


def test_session_rejects_malformed_theorem_fail_loud(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    pool = LeanSessionPool()
    try:
        verdict = pool.submit("def x : Nat := 1")
    finally:
        pool.close()
    assert verdict.status == "failed"
    assert "shape" in (verdict.native_output or "")


def test_proof_state_capture_and_resume_roundtrip(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # goal states are session-local: capture works on the session that opened
    # the namespace, and resume validates within that same session
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    session = PantographSession(session_command(str(stub_repl)))
    try:
        session.start_proof(FAILING_THEOREM)  # leaves an open namespace
        state = session.capture_proof_state()
        assert state.stateId is not None
        assert state.goals == ["∀ (a b : Int), a + b = b - a"]
        payload = state.to_payload()
        restored = LeanProofState.from_payload(payload)
        assert restored == state
        session.resume(restored)  # same session: validated
    finally:
        session.close()


def test_resume_across_sessions_fails_loud(
    stub_repl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PANTOGRAPH_ENV_VAR, str(stub_repl))
    first = PantographSession(session_command(str(stub_repl)))
    try:
        first.start_proof(FAILING_THEOREM)
        state = first.capture_proof_state()
    finally:
        first.close()
    second = PantographSession(session_command(str(stub_repl)))
    try:
        with pytest.raises(RuntimeError, match="session-local"):
            second.resume(state)
    finally:
        second.close()


def test_v1_proof_state_payload_is_rejected() -> None:
    # fail loud on a stale v1 payload (no stateId, old protocol_version)
    import json as _json

    v1 = _json.dumps({"theorem": "t", "goals": ["g"], "protocol_version": 1}, sort_keys=True)
    with pytest.raises(ValueError, match="protocol"):
        LeanProofState.from_payload(v1)


def test_proof_state_payload_is_storable_i5(tmp_path: Path) -> None:
    # the opaque payload format rides inside the frozen I5 schema (ADR 0001)
    from uvil.artifacts.proof import ProofPayload

    state = LeanProofState(theorem="theorem t : True := by trivial", stateId=7, goals=["False"])
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

# Windows: the built REPL needs the pinned toolchain's bin dir on PATH for the
# Lean DLLs (libleanshared.dll); discovery-documented in lean/README.md.
_TOOLCHAIN_BIN = (
    Path(os.environ.get("USERPROFILE", str(Path.home())))
    / ".elan"
    / "toolchains"
    / "leanprover--lean4---v4.33.1"
    / "bin"
)


@pytest.fixture
def live_toolchain_path(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name == "nt" and _TOOLCHAIN_BIN.exists():
        monkeypatch.setenv("PATH", str(_TOOLCHAIN_BIN) + os.pathsep + os.environ.get("PATH", ""))


@pytest.mark.skipif(not LIVE, reason="live pantograph-repl not provided (UVIL_PANTOGRAPH)")
def test_live_pantograph_attests_trivial_theorem(live_toolchain_path: None) -> None:
    pool = LeanSessionPool()
    try:
        verdict = pool.submit("theorem uvil_live : (1 : Int) + 1 = 2 := by omega")
    finally:
        pool.close()
    assert verdict.status == "attested", verdict.native_output


@pytest.mark.skipif(not LIVE, reason="live pantograph-repl not provided (UVIL_PANTOGRAPH)")
def test_live_pantograph_sorry_gate(live_toolchain_path: None) -> None:
    pool = LeanSessionPool()
    try:
        verdict = pool.submit("theorem uvil_live_sorry : (1 : Int) + 1 = 3 := by sorry")
    finally:
        pool.close()
    assert verdict.status == "failed"
    assert "sorry" in (verdict.native_output or "")
