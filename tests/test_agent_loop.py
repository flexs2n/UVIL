"""WI-4 agent-loop tests: transcript replay determinism + the reuse claim.

The committed transcript (`examples/agent_loop/transcript/transcript.json`)
is a recorded session of the repair loop against the incremental protocol.
Replaying it must reproduce, with zero network:

- the same iteration structure (2 iterations: cold refuted run -> repaired
  all-discharged run);
- the same per-iteration feedback JSONs (the I6/I7 common-JSON view);
- the same reused/recomputed partitions - the P5 claim: the untouched
  procedure's cached verdict survives the repair (iteration 2 reuses 1).

The live LLM arm (`LLMRepairAgent`) is env-gated (skip-if-absent): the
default suite never sets UVIL_AGENT_BASE_URL/UVIL_AGENT_MODEL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "examples" / "agent_loop"))

from agent import LLMRepairAgent, ScriptedReplayAgent  # noqa: E402
from loop import TRANSCRIPT_PATH, _assert_replay_matches, run_repair_loop  # noqa: E402

TRANSCRIPT = json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
PROGRAM = (REPO_ROOT / "examples" / "agent_loop" / "program.bpl").read_text(encoding="utf-8")


def test_transcript_records_the_repair_story() -> None:
    iterations = TRANSCRIPT["iterations"]
    assert len(iterations) == 2
    first, second = iterations
    # cold run: everything recomputes, the bug is refuted with I6+I7 feedback
    assert (first["reused"], first["recomputed"]) == (0, 2)
    assert first["agent_reply"] is not None
    kinds = {f["uvil_type"] for f in first["feedback"]}
    assert kinds == {"counterexample", "diagnostic"}
    # repaired run: the untouched procedure's verdict is reused, no solver call
    assert (second["reused"], second["recomputed"]) == (1, 1)
    assert all(v == "discharged" for v in second["verdicts"].values())
    assert TRANSCRIPT["final"]["all_discharged"] is True


def test_transcript_replay_is_deterministic(tmp_path: Path) -> None:
    replayed = run_repair_loop(PROGRAM, ScriptedReplayAgent(TRANSCRIPT), tmp_path)
    _assert_replay_matches(replayed, TRANSCRIPT)


def test_replay_reports_reuse_in_the_run_summary(tmp_path: Path) -> None:
    replayed = run_repair_loop(PROGRAM, ScriptedReplayAgent(TRANSCRIPT), tmp_path)
    (second,) = [it for it in replayed["iterations"] if it["iteration"] == 2]
    assert second["reused"] == 1 and second["recomputed"] == 1


def test_live_llm_agent_is_env_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UVIL_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("UVIL_AGENT_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="UVIL_AGENT_BASE_URL"):
        LLMRepairAgent()


@pytest.mark.skipif(
    not __import__("os").environ.get("UVIL_AGENT_BASE_URL"),
    reason="live LLM arm: UVIL_AGENT_BASE_URL not set (never set in the default suite)",
)
def test_live_llm_agent_repairs_end_to_end(tmp_path: Path) -> None:
    agent = LLMRepairAgent()
    transcript = run_repair_loop(PROGRAM, agent, tmp_path)
    assert transcript["final"]["all_discharged"] is True
