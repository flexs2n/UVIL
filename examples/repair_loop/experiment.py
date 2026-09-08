"""Two-arm repair experiment over the failure corpus subset the stubs target.

Arms (both consume deterministic stub agents; no LLM/network):

- standardized: ONE agent (`StubRepairer`) fed common-JSON feedback, repairing
  z3 refutations AND Boogie-parser failures unchanged.
- native: bespoke per-backend agents (`NativeZ3Repairer` reading raw z3 model
  sexprs, `NativeBoogieRepairer` reading raw parser error text), selected per
  entry by backend-specific dispatch.

Subsets:
- refuted: 30 generated wrong-constant instances (`requires a == N` with a
  deliberately wrong `assert a + a == K;`), same discipline as the corpus
  refutation families.
- parse: 80 `parse-*` entries from `corpora/failures/` (if/call/uninterp/type;
  the `parse-stray` family is outside the stubs' contract - repairing a stray
  token still leaves a refutable claim, which no stub is scoped to de-scope).

Reported per arm: success counts and lines of backend-specific agent code.
Results are written to RESULTS.md (committed; the numbers are deterministic).

Usage: .venv/Scripts/python.exe examples/repair_loop/experiment.py
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents import NativeBoogieRepairer, NativeZ3Repairer, StubRepairer  # noqa: E402
from harness import NATIVE_FORM, RepairAgent, run_loop  # noqa: E402

FAILURES_DIR = REPO_ROOT / "corpora" / "failures"
RESULTS_PATH = Path(__file__).resolve().parent / "RESULTS.md"

REFUTED_INSTANCES = 30
PARSE_FAMILIES = ["parse-if", "parse-call", "parse-uninterp", "parse-type"]
MAX_ITERATIONS = 6


def wrong_constant_source(n: int, k: int) -> str:
    return f"procedure p_fix_{n}(a: int)\n  requires a == {n}\n{{\n  assert a + a == {k};\n}}\n"


def load_entries() -> list[tuple[str, str, str]]:
    """(entry_id, backend, source) for the targeted corpus subset."""
    manifest = json.loads((FAILURES_DIR / "expected.json").read_text(encoding="utf-8"))
    entries: list[tuple[str, str, str]] = []
    for entry_id in sorted(manifest["expected"]):
        entry = manifest["expected"][entry_id]
        if entry["family"] not in PARSE_FAMILIES:
            continue
        source = (FAILURES_DIR / entry["file"]).read_text(encoding="utf-8")
        entries.append((entry_id, entry["backend"], source))
    return entries


def build_subsets() -> list[tuple[str, str, str]]:
    entries = [
        ("refuted/wrong-constant", "z3", wrong_constant_source(n, 2 * n + 1))
        for n in range(1, REFUTED_INSTANCES + 1)
    ]
    entries += load_entries()
    return entries


def measure(arm: str, entries: list[tuple[str, str, str]]) -> dict[str, object]:
    outcomes = []
    for entry_id, entry_backend, source in entries:
        if arm == "standardized":
            agent: RepairAgent = StubRepairer()
            outcome = run_loop(source, agent, max_iterations=MAX_ITERATIONS)
        else:
            # bespoke per-backend dispatch: a different agent object per backend
            agent = NativeZ3Repairer() if entry_backend == "z3" else NativeBoogieRepairer()
            outcome = run_loop(
                source, agent, max_iterations=MAX_ITERATIONS, feedback_form=NATIVE_FORM
            )
        outcomes.append((entry_id, outcome.success, outcome.iterations, outcome.stop_reason))
    successes = sum(1 for _, ok, _, _ in outcomes if ok)
    return {
        "arm": arm,
        "total": len(outcomes),
        "successes": successes,
        "failures": [
            {"entry": e, "iterations": i, "stop": s} for e, ok, i, s in outcomes if not ok
        ],
    }


def loc_of(*classes: type) -> int:
    return sum(len(inspect.getsource(c).splitlines()) for c in classes)


def main() -> int:
    entries = build_subsets()
    standardized = measure("standardized", entries)
    native = measure("native", entries)
    standardized_loc = loc_of(StubRepairer) + 0  # common-JSON consumers only
    native_loc = loc_of(NativeZ3Repairer, NativeBoogieRepairer)

    lines = [
        "# Repair-loop experiment results (deterministic stubs)",
        "",
        "Interface demonstration, not repair power: both arms are deterministic",
        "rule-based stubs scoped to the named corpus families. The measured claim",
        "is interface uniformity - ONE standardized agent repairs z3 refutations",
        "and Boogie-parser failures unchanged (the M2 exit criterion) - not that",
        "de-scoping repairs are meaningful program fixes.",
        "",
        "| arm | entries | successes | backend-specific agent LOC |",
        "|---|---|---|---|",
        f"| standardized (common JSON, one agent) | {standardized['total']} "
        f"| {standardized['successes']} | {standardized_loc} |",
        f"| native (raw backend text, per-backend agents) | {native['total']} "
        f"| {native['successes']} | {native_loc} |",
        "",
        "## Subsets",
        "",
        f"- refuted: {REFUTED_INSTANCES} generated wrong-constant instances",
        f"- parse: {len(entries) - REFUTED_INSTANCES} corpus entries from "
        f"{'/'.join(PARSE_FAMILIES)} (parse-stray is outside the stubs' contract)",
        "",
        "## Standardized-arm failures",
        "",
    ]
    if standardized["failures"]:
        lines += [f"- {f}" for f in standardized["failures"]]  # type: ignore[union-attr]
    else:
        lines.append("- none")
    lines += ["", "## Native-arm failures", ""]
    if native["failures"]:
        lines += [f"- {f}" for f in native["failures"]]  # type: ignore[union-attr]
    else:
        lines.append("- none")
    lines.append("")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {RESULTS_PATH}")
    print(
        f"standardized: {standardized['successes']}/{standardized['total']} "
        f"(agent LOC {standardized_loc})"
    )
    print(f"native:       {native['successes']}/{native['total']} (agent LOC {native_loc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
