# Demo: a real repair agent on the incremental protocol (WI-4, the W3 fix)

The repair loop the M5 protocol was built for, exercised by a real consumer:

    program -> import (WP) -> check_incremental (z3, verdict cache)
            -> common-JSON feedback (I6/I7) -> agent -> repaired program
            -> re-check incrementally (reused/recomputed per iteration)

The agent consumes ONLY the common-JSON feedback view
(`uvil.render.to_common_json`) - never native solver output - and returns the
complete repaired program. Untouched procedures keep byte-identical fragments,
so their obligations' identities are stable and their cached verdicts are
reused with no solver call: the P5 claim, finally measured by a consumer.

## Layout

- `agent.py` — the repair interface, three ways:
  - `LLMRepairAgent` — any OpenAI-compatible chat endpoint over plain stdlib
    HTTP (no provider SDK). Env-gated: `UVIL_AGENT_BASE_URL`,
    `UVIL_AGENT_MODEL`, `UVIL_AGENT_KEY`; unset, it refuses to construct and
    the default suite skips the live arm.
  - `DemoRepairAgent` — the deterministic rule-based repairer that recorded
    the committed transcript (a real loop session, zero network).
  - `ScriptedReplayAgent` — replays a committed transcript verbatim.
- `loop.py` — `run_repair_loop` + the CLI modes (replay | `--record` | `--live`).
- `program.bpl` — the repair target: `clamp_ok` (correct, untouched by the
  repair) and `clamp_step` (the refuted bug).
- `transcript/transcript.json` — the recorded session: per-iteration program,
  feedback JSONs, agent reply, and the reused/recomputed partition. Recorded
  against a fresh state so the numbers are reproducible; the meta records
  which agent produced it (re-record with a live LLM via `--live`).

## The recorded session (2 iterations)

1. cold: 2 obligations, `0 reused / 2 recomputed` - `clamp_step`'s assert is
   refuted; the agent receives the I6 valuation (x == k) + I7 as common JSON.
2. repaired: the agent saturates the increment; `clamp_ok`'s cached verdict is
   REUSED (1 reused / 1 recomputed) and the repaired procedure discharges.

## Run

```sh
# the deterministic replay CI and reviewers see (zero network):
python examples/agent_loop/loop.py --state .uvil-agent-replay

# re-record with the deterministic repairer:
python examples/agent_loop/loop.py --record

# record a session with a live LLM (any OpenAI-compatible provider):
UVIL_AGENT_BASE_URL=https://api.example.com/v1 UVIL_AGENT_MODEL=... \
  python examples/agent_loop/loop.py --live
```

Replay asserts the recorded feedback and reuse numbers reproduce exactly;
drift is a hard error.
