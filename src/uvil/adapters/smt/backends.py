"""Solver backends: in-process z3 (pinned) and optional subprocess cvc5.

Verdict mapping is total and fail-loud: `unsat -> discharged`, `sat -> refuted`,
`unknown -> unknown` (+ I7), `timeout -> timeout` (+ I7). **No code path may
upgrade an unknown/timeout verdict to discharged** - `verdict_status` is the
single mapping point and is unit-tested for that invariant.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...artifacts import ObligationStatus

CVC5_ENV_VAR = "UVIL_CVC5"

# Hard pin per docs/decisions/0002-tool-pinning.md (z3-solver pip wheel).
PINNED_Z3 = "5.1.0"

VerdictStatus = Literal["unsat", "sat", "unknown", "timeout"]


@dataclass(frozen=True)
class SmtVerdict:
    status: VerdictStatus
    model: str | None
    solver_version: str
    time_ms: int | None


def verdict_status(verdict: SmtVerdict) -> ObligationStatus:
    """The single verdict->status mapping point. Unknown/timeout never discharge.

    `unknown` maps to `open` (the I4 model has no unknown status): the obligation
    stays open and an I7 diagnostic of kind=unknown travels with it.
    """
    mapping: dict[VerdictStatus, ObligationStatus] = {
        "unsat": "discharged",
        "sat": "refuted",
        "unknown": "open",
        "timeout": "timeout",
    }
    return mapping[verdict.status]


class Z3Backend:
    name = "z3"

    def __init__(self) -> None:
        import z3  # type: ignore[import-untyped]

        version = z3.get_version_string()
        if version != PINNED_Z3:
            raise RuntimeError(
                f"z3-solver {version} is installed but the pin requires {PINNED_Z3} "
                "(docs/decisions/0002-tool-pinning.md)"
            )
        self._z3 = z3

    def run(self, assertions: str, solver_ms: int | None = None) -> SmtVerdict:
        import time

        z3 = self._z3
        start = time.perf_counter()
        solver = z3.Solver()
        if solver_ms is not None:
            solver.set("timeout", solver_ms)
        solver.from_string(assertions)
        result = solver.check()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if result == z3.sat:
            status: VerdictStatus = "sat"
        elif result == z3.unsat:
            status = "unsat"
        else:
            reason = str(solver.reason_unknown())
            status = "timeout" if "timeout" in reason.lower() else "unknown"
        model = str(solver.model().sexpr()) if status == "sat" else None
        return SmtVerdict(
            status=status,
            model=model,
            solver_version=z3.get_version_string(),
            time_ms=elapsed_ms,
        )


class Cvc5Backend:
    name = "cvc5"

    def __init__(self, executable: str | None = None) -> None:
        resolved = executable or os.environ.get(CVC5_ENV_VAR)
        if not resolved:
            raise RuntimeError(
                f"cvc5 backend is optional: set {CVC5_ENV_VAR} to a pinned cvc5 binary"
            )
        self.executable = resolved

    def version(self) -> str:
        proc = subprocess.run(
            [self.executable, "--version"], capture_output=True, text=True, check=False
        )
        for token in proc.stdout.split():
            if token[0].isdigit():
                return token
        raise RuntimeError(f"cannot parse cvc5 version from: {proc.stdout!r}")

    def run(self, script: str, solver_ms: int | None = None) -> SmtVerdict:
        import time

        args = [self.executable, "--produce-models", "--force-logic=ALL"]
        if solver_ms is not None:
            args.append(f"--tlimit={solver_ms}")
        with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = Path(f.name)
        try:
            start = time.perf_counter()
            proc = subprocess.run([*args, str(path)], capture_output=True, text=True, check=False)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
        finally:
            path.unlink(missing_ok=True)
        return self._parse_output(proc.stdout, elapsed_ms)

    def _parse_output(self, output: str, elapsed_ms: int) -> SmtVerdict:
        lines = [
            ln.strip() for ln in output.splitlines() if ln.strip() and not ln.startswith("cvc5")
        ]
        for i, line in enumerate(lines):
            if line in ("sat", "unsat", "unknown"):
                status: VerdictStatus = line  # type: ignore[assignment]
                model = self._extract_model(lines[i + 1 :]) if line == "sat" else None
                return SmtVerdict(
                    status=status, model=model, solver_version=self.version(), time_ms=elapsed_ms
                )
        # no verdict line at all: treat as unknown, never as success
        return SmtVerdict(
            status="unknown", model=None, solver_version=self.version(), time_ms=elapsed_ms
        )

    @staticmethod
    def _extract_model(lines: list[str]) -> str:
        return "\n".join(lines) if lines else "(model unavailable)"
