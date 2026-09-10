"""The agent repair loop wired to the M5 incremental protocol (WI-4).

`run_repair_loop` is the real consumer the incremental protocol was built for
(P5): the baseline check primes the verdict cache; every repair iteration
re-imports the (edited) program and re-checks INCREMENTALLY - untouched
procedures' obligations reuse their cached verdicts with no solver call, the
edited procedure recomputes. Each iteration records the reused/recomputed
partition in the run summary.

Feedback contract: the agent sees ONLY common-JSON renderings of the I6
counterexamples and I7 diagnostics (`uvil.render.to_common_json`) - never
native solver output, never UVIL internals.

Modes:
- default (replay): the agent is `ScriptedReplayAgent` over the committed
  transcript; the loop must reproduce the recorded feedback and reuse numbers
  exactly (deterministic, zero network) - this is what CI and reviewers see.
- `--record`: run with `DemoRepairAgent` (the deterministic repairer that
  produced the committed transcript) and (re)write
  `transcript/transcript.json` from this real session.
- `--live`: run with `LLMRepairAgent` (env-gated: UVIL_AGENT_BASE_URL /
  UVIL_AGENT_MODEL / UVIL_AGENT_KEY); writes the same transcript shape so a
  live LLM session can be committed the same way.

The state directory is scratch (cache + ledger - reproducible run state, not
evidence); the committed evidence is the transcript plus the program files.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.artifacts import Counterexample, Diagnostic  # noqa: E402
from uvil.ledger import Ledger  # noqa: E402
from uvil.protocol import check_incremental  # noqa: E402
from uvil.render import to_common_json  # noqa: E402
from uvil.store import ContentStore  # noqa: E402

TRANSCRIPT_PATH = Path(__file__).resolve().parent / "transcript" / "transcript.json"
PROGRAM_PATH = Path(__file__).resolve().parent / "program.bpl"
MAX_ITERATIONS = 4


def _feedback(result) -> list[dict[str, Any]]:
    """The common-JSON view of one check result: I6s then I7s, sorted by ref."""
    items: list[Counterexample | Diagnostic] = [
        *result.counterexamples,
        *result.diagnostics,
    ]
    return [to_common_json(item) for item in items]


def run_repair_loop(
    source: str, agent, state: Path, max_iterations: int = MAX_ITERATIONS
) -> dict[str, Any]:
    store = ContentStore(state)
    ledger = Ledger(state / "ledger.jsonl")
    transcript: dict[str, Any] = {
        "meta": {
            "program": PROGRAM_PATH.name,
            "z3_pin": "5.1.0",
            "protocol": "uvil incremental check (M5) via check_incremental",
            "agent": type(agent).__name__,
        },
        "iterations": [],
    }
    current = source
    for iteration in range(1, max_iterations + 1):
        result = import_module(current, "program.bpl")
        if not result.ok:
            raise RuntimeError(
                "the agent produced an out-of-subset program: "
                f"{[d.native_message for d in result.diagnostics]}"
            )
        obligations = [o for p in result.procedures.values() for o in p.obligations]
        checked = check_incremental(obligations, store, ledger, backend="z3")
        assert checked.result.run is not None
        verdicts = {
            v.obligation_ref.rsplit(":", 1)[-1][:16]: v.status for v in checked.result.run.verdicts
        }
        entry: dict[str, Any] = {
            "iteration": iteration,
            "program": current,
            "obligations": len(obligations),
            "reused": len(checked.reused),
            "recomputed": len(checked.recomputed),
            "verdicts": verdicts,
            "feedback": _feedback(checked.result),
            "agent_reply": None,
        }
        transcript["iterations"].append(entry)
        if all(v == "discharged" for v in verdicts.values()):
            break
        if iteration == max_iterations:
            raise RuntimeError("the repair loop did not converge within budget")
        reply = agent.reply(iteration, current, entry["feedback"])
        entry["agent_reply"] = {"program": reply}
        current = reply
    transcript["final"] = {
        "all_discharged": all(
            v == "discharged" for v in transcript["iterations"][-1]["verdicts"].values()
        ),
    }
    return transcript


def main() -> int:
    parser = argparse.ArgumentParser(description="the UVIL agent repair loop")
    parser.add_argument("--program", type=Path, default=PROGRAM_PATH)
    parser.add_argument("--state", type=Path, default=Path(".uvil-agent"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--record", action="store_true", help="record a new transcript (DemoRepairAgent)"
    )
    mode.add_argument("--live", action="store_true", help="record with the env-gated LLM agent")
    args = parser.parse_args()

    from agent import DemoRepairAgent, LLMRepairAgent, ScriptedReplayAgent

    source = args.program.read_text(encoding="utf-8")
    if args.live or args.record:
        agent = LLMRepairAgent() if args.live else DemoRepairAgent()
        # a transcript is only reproducible if it was recorded against a FRESH
        # state: reused/recomputed numbers describe the run from an empty cache
        with tempfile.TemporaryDirectory(prefix="uvil-agent-loop-") as fresh:
            transcript = run_repair_loop(source, agent, Path(fresh))
        TRANSCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        TRANSCRIPT_PATH.write_text(
            json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"recorded {TRANSCRIPT_PATH}")
        return 0
    transcript = run_repair_loop(source, ScriptedReplayAgent(_load_transcript()), args.state)
    _assert_replay_matches(transcript, _load_transcript())
    print("replay ok: feedback and reuse numbers match the committed transcript")
    return 0


def _load_transcript() -> dict[str, Any]:
    return json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))


def _assert_replay_matches(replayed: dict[str, Any], recorded: dict[str, Any]) -> None:
    """Replay is the recorded session's twin: same programs, feedback, reuse."""
    if len(replayed["iterations"]) != len(recorded["iterations"]):
        raise RuntimeError("replay iteration count drifted from the transcript")
    for replayed_it, recorded_it in zip(
        replayed["iterations"], recorded["iterations"], strict=True
    ):
        for field in ("program", "obligations", "reused", "recomputed", "verdicts", "feedback"):
            if replayed_it[field] != recorded_it[field]:
                raise RuntimeError(f"replay drift at iteration {replayed_it['iteration']}: {field}")


if __name__ == "__main__":
    raise SystemExit(main())
