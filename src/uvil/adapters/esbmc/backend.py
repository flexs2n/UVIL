"""Pinned ESBMC backend: bounded model checking of C harnesses.

ESBMC (scalable C/C++ bounded model checker, github.com/esbmc/esbmc) is the
model-checking backend whose frontend is NOT Boogie: it compiles real C (its
own frontend + GOTO conversion), so it verifies harnesses no Boogie-only path
could carry — the M4 cross-language requirement.

Fail-loud pins (ADR 0002 discipline; ADR 0004 documents the binary pin):
- absent esbmc        -> `EsbmcNotInstalled` (tests self-skip, CLI skips exit 0)
- present-but-mismatched -> `EsbmcVersionMismatch` hard error, never a silent
  check under the wrong binary

`UVIL_ESBMC` overrides the binary location (cvc5 precedent). Discovery pins
(v8.5 Windows binary, see tests/test_esbmc_discovery.py):
- verdict lines `VERIFICATION SUCCESSFUL` / `VERIFICATION FAILED` (exit 0/1);
  parse errors exit 6; `VERIFICATION UNKNOWN` is printed for out-of-resource
  runs; anything else is `unknown` — never upgraded.
- `--timeout` is UNIMPLEMENTED on Windows (`ERROR: Timeout unimplemented on
  Windows, sorry`), so the budget is enforced by the subprocess layer here.
- `--bug-finding` does NOT exist in v8.5 (`unrecognised option`); the
  documented multi-property mode is `--multi-property`. The plan's
  `[--bug-finding]` CLI option maps to that real flag.
- `--generate-json-report` emits `report.json` (CWD of the process) when a
  violation is found and nothing otherwise; `cex.py` parses it into I6 Trace.

Verdict mapping (`esbmc_status`) is TOTAL and fail-loud: model-checking
results NEVER discharge a deductive obligation and NEVER refute one — a
violated harness is a bounded execution witness (I6 Trace), not a deductive
refutation; a verified harness is a bounded run record, not a kernel
guarantee. No code path may upgrade any ESBMC verdict to `discharged`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...artifacts import ObligationStatus

# Hard pin per docs/decisions/0002-tool-pinning.md; the v8.5 release asset
# esbmc-windows.zip carries sha256 626c91e587ec496d1e5fdc523cf8d557627af27087b4c13f0f3c241d286b3a55.
PINNED_ESBMC = "8.5.0"
ESBMC_RELEASE_TAG = "v8.5"

# cvc5 precedent: env-var override for the binary location.
ESBMC_ENV_VAR = "UVIL_ESBMC"

# Documented default install dir of the pinned release binary (ADR 0004).
_DEFAULT_BIN_DIR = (
    Path.home() / "tools" / f"esbmc-{ESBMC_RELEASE_TAG.lstrip('v')}" / "release" / "bin"
)

EsbmcStatus = Literal["verified", "violated", "unknown", "timeout"]


class EsbmcNotInstalled(RuntimeError):
    """ESBMC is not available on this machine (skip-if-absent paths)."""


class EsbmcVersionMismatch(RuntimeError):
    """A present-but-unpinned ESBMC binary - hard error, never a warning."""


@dataclass(frozen=True)
class EsbmcVerdict:
    status: EsbmcStatus
    esbmc_version: str
    time_ms: int | None
    raw_output: str
    # Raw text of the JSON report emitted by --generate-json-report on a
    # violation (None on success/unknown/timeout). Parsed by `cex.py`.
    report_json: str | None


def esbmc_status(verdict: EsbmcVerdict) -> ObligationStatus:
    """The single verdict->status mapping point. Total and fail-loud.

    Model-checking results never discharge a deductive obligation and never
    refute one: `verified`/`violated`/`unknown` all leave the obligation
    `open` (the evidence travels as an I8 run record, I6 trace, and I7
    diagnostic - never as an I4 status upgrade); `timeout` maps to the I4
    `timeout` status exactly like the SMT backend (still no discharge).
    """
    mapping: dict[EsbmcStatus, ObligationStatus] = {
        "verified": "open",
        "violated": "open",
        "unknown": "open",
        "timeout": "timeout",
    }
    return mapping[verdict.status]


def find_esbmc() -> str:
    """Locate the pinned ESBMC binary: `UVIL_ESBMC` override, PATH, then the
    documented default install dir (ADR 0004)."""
    override = os.environ.get(ESBMC_ENV_VAR)
    if override:
        if Path(override).exists():
            return override
        raise EsbmcNotInstalled(
            f"{ESBMC_ENV_VAR} points at a missing binary: {override} "
            f"(pin: {ESBMC_RELEASE_TAG}, expected version {PINNED_ESBMC})"
        )
    found = shutil.which("esbmc")
    if found:
        return found
    exe = _DEFAULT_BIN_DIR / ("esbmc.exe" if os.name == "nt" else "esbmc")
    if exe.exists():
        return str(exe)
    raise EsbmcNotInstalled(
        f"esbmc is not installed (set {ESBMC_ENV_VAR} to the pinned "
        f"{ESBMC_RELEASE_TAG} release binary, expected version {PINNED_ESBMC})"
    )


class EsbmcBackend:
    name = "esbmc"

    def __init__(self) -> None:
        self.executable = find_esbmc()
        self.esbmc_version = self._verify_version()

    def _verify_version(self) -> str:
        proc = subprocess.run(
            [self.executable, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        match = re.search(r"ESBMC version (\S+)", output)
        if proc.returncode != 0 or match is None:
            raise EsbmcVersionMismatch(f"cannot determine esbmc version from: {output!r}")
        version = match.group(1)
        if version != PINNED_ESBMC:
            raise EsbmcVersionMismatch(
                f"esbmc {version} is installed but the pin requires {PINNED_ESBMC} "
                f"({ESBMC_RELEASE_TAG} release binary; docs/decisions/0002-tool-pinning.md)"
            )
        return version

    def run_source(
        self, source: str, filename: str = "harness.c", timeout_s: float | None = None
    ) -> EsbmcVerdict:
        """Run ESBMC on one C harness; returns the verdict + raw JSON report.

        The harness source is written to a temp dir (ESBMC itself compiles the
        real source - UVIL's import parser is only for obligation extraction
        and is never trusted for the check). The subprocess timeout is the
        only budget mechanism on Windows (`--timeout` is unimplemented there,
        discovery-pinned)."""
        with tempfile.TemporaryDirectory(prefix="uvil-esbmc-") as tmp:
            workdir = Path(tmp)
            harness = workdir / Path(filename).name
            harness.write_text(source, encoding="utf-8", newline="\n")
            args = [self.executable, "--generate-json-report", str(harness)]
            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=False,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_s,
                    cwd=workdir,
                )
            except subprocess.TimeoutExpired:
                return EsbmcVerdict(
                    status="timeout",
                    esbmc_version=self.esbmc_version,
                    time_ms=int((time.perf_counter() - start) * 1000),
                    raw_output=(
                        f"esbmc exceeded the {timeout_s}s subprocess budget "
                        "(--timeout is unimplemented on Windows; budget enforced "
                        "by the subprocess layer)"
                    ),
                    report_json=None,
                )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            output = (proc.stdout + "\n" + proc.stderr).strip()
            report_path = workdir / "report.json"
            report_json = report_path.read_text(encoding="utf-8") if report_path.exists() else None
        return EsbmcVerdict(
            status=_classify(output),
            esbmc_version=self.esbmc_version,
            time_ms=elapsed_ms,
            raw_output=output,
            report_json=report_json,
        )

    def report_of(self, verdict: EsbmcVerdict) -> list[dict[str, object]]:
        """Parsed JSON-report entries of a verdict (empty when absent)."""
        if verdict.report_json is None:
            return []
        parsed = json.loads(verdict.report_json)
        if not isinstance(parsed, list):
            raise ValueError(f"unexpected esbmc report.json shape: {type(parsed).__name__}")
        return [entry for entry in parsed if isinstance(entry, dict)]


def _classify(output: str) -> EsbmcStatus:
    """Verdict-line classification (discovery-pinned strings). Unknown shapes
    stay unknown - never upgraded."""
    if "VERIFICATION SUCCESSFUL" in output:
        return "verified"
    if "VERIFICATION FAILED" in output:
        return "violated"
    return "unknown"
