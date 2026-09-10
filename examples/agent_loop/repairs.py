"""The repair rules behind the committed transcript's recorded session.

Separated from `agent.py` so the agent surface stays exactly the three
implementations of the repair interface. Each rule fires on the iteration
number and asserts the expected feedback shape before producing the repair
(fail loud on drift, never a silent mismatch).
"""

from __future__ import annotations

from typing import Any

# v0: clamp_step's second assert is refuted (I6 valuation: x == k makes y = x+1
# exceed k). Repair: saturate the increment at k instead of over-shooting.
_V1 = """\
// repair 1: saturate the increment at k (the I6 witness had x == k)
procedure clamp_ok(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  var y: int;
  y := x;
  assert y >= -k && y <= k;
}

procedure clamp_step(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  var y: int;
  y := x;
  y := (if x + 1 > k then k else x + 1);
  assert y <= k;
}
"""

# v2: a sharper post-step claim is added (provable: y is min(x+1, k) with
# x >= -k); clamp_ok stays byte-identical so its cached verdict is reused.
_V2 = """\
// repair 2: add the sharper two-sided post-step claim
procedure clamp_ok(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  var y: int;
  y := x;
  assert y >= -k && y <= k;
}

procedure clamp_step(x: int, k: int)
  requires k >= 1 && x >= -k && x <= k
{
  var y: int;
  y := x;
  y := (if x + 1 > k then k else x + 1);
  assert y <= k;
  assert y >= 1 - k;
}
"""

_EXPECTED_FEEDBACK: dict[int, set[str]] = {
    # I6 `counterexample` + I7 `diagnostic` (the unproved-refutation note);
    # common-JSON keys by artifact type, not native kind
    1: {"counterexample", "diagnostic"},
    2: set(),  # v1 was fully discharged: the loop ended before this rule fires
}


def repair_for(iteration: int, program: str, feedback: list[dict[str, Any]]) -> str:
    del program
    kinds = {f["uvil_type"] for f in feedback if f.get("uvil_type")}
    expected = _EXPECTED_FEEDBACK.get(iteration, set())
    if kinds != expected:
        raise RuntimeError(
            f"repair rule {iteration}: expected feedback kinds {expected}, got {kinds}"
        )
    if iteration == 1:
        return _V1
    if iteration == 2:
        return _V2
    raise RuntimeError(f"no repair rule for iteration {iteration}")
