"""Repair agents for the agent-loop example (WI-4).

Every agent consumes ONLY the common-JSON feedback the harness provides
(`uvil.render.to_common_json` I6/I7 shapes) and returns the complete repaired
program text - one interface, three implementations:

- `LLMRepairAgent`: any OpenAI-compatible chat endpoint (plain stdlib HTTP,
  no provider SDK). Env-gated: `UVIL_AGENT_BASE_URL`, `UVIL_AGENT_MODEL`,
  `UVIL_AGENT_KEY`; without them it refuses to construct (the live arm is
  skip-if-absent everywhere, like every optional backend).
- `DemoRepairAgent`: the deterministic rule-based repairer that recorded the
  committed transcript (a real session of the loop, zero network).
- `ScriptedReplayAgent`: replays a committed transcript's replies verbatim -
  the deterministic replay CI and reviewers rely on.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

BASE_URL_ENV = "UVIL_AGENT_BASE_URL"
MODEL_ENV = "UVIL_AGENT_MODEL"
KEY_ENV = "UVIL_AGENT_KEY"

_SYSTEM_PROMPT = (
    "You repair verification programs. You receive UVIL common-JSON feedback: "
    "I6 counterexamples (a refuting valuation for one obligation) and I7 "
    "diagnostics. Reply with the complete repaired Boogie program and nothing "
    "else. Keep every procedure you do not need to change byte-identical."
)


class RepairAgent(Protocol):
    def reply(self, iteration: int, program: str, feedback: list[dict[str, Any]]) -> str: ...


@dataclass
class LLMRepairAgent:
    """Generic OpenAI-compatible repair agent (stdlib HTTP, env-gated)."""

    base_url: str
    model: str
    key: str

    def __init__(self) -> None:
        base_url = os.environ.get(BASE_URL_ENV)
        model = os.environ.get(MODEL_ENV)
        key = os.environ.get(KEY_ENV, "")
        if not base_url or not model:
            raise RuntimeError(
                f"the live LLM arm requires {BASE_URL_ENV} and {MODEL_ENV} "
                "(skip-if-absent: the default suite never sets them)"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.key = key

    def reply(self, iteration: int, program: str, feedback: list[dict[str, Any]]) -> str:
        del iteration
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"program": program, "feedback": feedback}, sort_keys=True
                        ),
                    },
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        return str(body["choices"][0]["message"]["content"])


class DemoRepairAgent:
    """The deterministic repairer that recorded the committed transcript.

    Rule-based on purpose: it reacts to the I6 valuation's variable names (the
    only feedback signal it uses) with the saturating-clamp repair, so the
    recorded session is reproducible without any network or provider.
    """

    _REPAIRS: dict[int, str] = {}

    def reply(self, iteration: int, program: str, feedback: list[dict[str, Any]]) -> str:
        from repairs import repair_for

        return repair_for(iteration, program, feedback)


class ScriptedReplayAgent:
    """Replays a committed transcript's agent replies verbatim (zero network)."""

    def __init__(self, transcript: dict[str, Any]) -> None:
        self._replies = {
            it["iteration"]: it["agent_reply"]["program"]
            for it in transcript["iterations"]
            if it.get("agent_reply") is not None
        }

    def reply(self, iteration: int, program: str, feedback: list[dict[str, Any]]) -> str:
        del program, feedback
        return self._replies[iteration]  # KeyError = transcript drift: fail loud
