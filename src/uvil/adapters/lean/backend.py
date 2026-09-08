"""Pinned Lean compile backend: standalone `lean file.lean` attestation.

Attestation = exit-0 of the pinned toolchain's kernel on a standalone proof
file. **Offline verifiability:** anyone with the pinned toolchain can re-run
`lean` on the stored file - no UVIL code, no network, no solver (R1: UVIL
records kernel work, it never re-verifies it; the hash lets third parties
detect tampering and replay the check themselves).

Fail-loud pins (ADR 0002):
- absent lean/elan      -> `LeanNotInstalled` (tests self-skip, CLI skips)
- present-but-mismatched -> `LeanVersionMismatch` hard error, never a
  silent check under the wrong kernel

The verdict->status mapping is total and fail-loud: `attested -> discharged`,
`failed -> open` (+ I7 unproved), `timeout -> open` (+ I7 timeout). **No code
path may upgrade a failed/timeout proof search to discharged** - proof-search
failure produces no counterexample, so nothing is ever `refuted` via Lean.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...artifacts import ObligationStatus

# Hard pin per docs/decisions/0002-tool-pinning.md; matches lean/lean-toolchain.
PINNED_LEAN = "4.33.1"
TOOLCHAIN_ID = f"leanprover/lean4:v{PINNED_LEAN}"

# ~25 theorems/file amortizes the measured ~1-4s cold start (discovery test).
LEAN_BATCH_SIZE = 25

LeanStatus = Literal["attested", "failed", "timeout"]


class LeanNotInstalled(RuntimeError):
    """lean/elan is not available on this machine (skip-if-absent paths)."""


class LeanVersionMismatch(RuntimeError):
    """A present-but-unpinned Lean toolchain - hard error, never a warning."""


@dataclass(frozen=True)
class LeanVerdict:
    status: LeanStatus
    kernel_version: str
    file_digest: str
    time_ms: int | None
    native_output: str | None


def lean_status(verdict: LeanVerdict) -> ObligationStatus:
    """The single verdict->status mapping point. Failed/timeout never discharge
    and never refute: a proof-search failure produces no counterexample."""
    mapping: dict[LeanStatus, ObligationStatus] = {
        "attested": "discharged",
        "failed": "open",
        "timeout": "open",
    }
    return mapping[verdict.status]


def proof_file_bytes(theorem: str) -> bytes:
    """The exact standalone .lean file bytes for a theorem (the I5 inline
    payload is byte-identical to this, which is what makes offline replay
    possible)."""
    return theorem.encode("utf-8")


def kernel_hash(theorem: str) -> str:
    """sha256(proof-file bytes + toolchain id) - the recorded attestation."""
    h = hashlib.sha256()
    h.update(proof_file_bytes(theorem))
    h.update(TOOLCHAIN_ID.encode("utf-8"))
    return h.hexdigest()


def find_lean() -> str:
    """Locate a lean executable (PATH first, then the standard elan shims)."""
    found = shutil.which("lean")
    if found:
        return found
    local = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".elan" / "bin" / "lean.exe"
    if local.exists():
        return str(local)
    raise LeanNotInstalled(
        "lean is not installed (no elan toolchain found); install the pinned "
        f"toolchain {TOOLCHAIN_ID} via elan"
    )


class LeanBackend:
    name = "lean4"

    def __init__(self, check_timeout_s: float | None = None) -> None:
        self.executable = find_lean()
        self.check_timeout_s = check_timeout_s
        self.kernel_version = self._verify_version()

    def env(self) -> dict[str, str]:
        """Environment pinning the toolchain for the elan shim (the caller's
        environment may have no default toolchain configured)."""
        env = dict(os.environ)
        env["ELAN_TOOLCHAIN"] = TOOLCHAIN_ID
        return env

    def _verify_version(self) -> str:
        proc = subprocess.run(
            [self.executable, "--version"],
            capture_output=True,
            text=True,
            check=False,
            env=self.env(),
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode != 0 or "version" not in output:
            raise LeanVersionMismatch(f"cannot determine lean version from: {output!r}")
        between = output.split("version", 1)[1].split(",", 1)[0].strip()
        if between != PINNED_LEAN:
            raise LeanVersionMismatch(
                f"lean {between} is installed but the pin requires {PINNED_LEAN} "
                f"({TOOLCHAIN_ID}; docs/decisions/0002-tool-pinning.md)"
            )
        return between

    def check_batch(self, theorems: list[str]) -> list[LeanVerdict]:
        """Attest theorems in batched standalone files; returns one verdict per
        theorem, aligned with the input. A failing batch is re-run per theorem
        so failures attribute exactly."""
        verdicts: list[LeanVerdict] = []
        for start in range(0, len(theorems), LEAN_BATCH_SIZE):
            chunk = theorems[start : start + LEAN_BATCH_SIZE]
            verdicts.extend(self._check_chunk(chunk))
        return verdicts

    def _check_chunk(self, theorems: list[str]) -> list[LeanVerdict]:
        content = "\n".join(theorems) + "\n"
        (exit0, _, elapsed_ms) = self._run_lean(content, "batch")
        if exit0:
            return [
                LeanVerdict(
                    status="attested",
                    kernel_version=self.kernel_version,
                    file_digest=kernel_hash(t),
                    time_ms=elapsed_ms // len(theorems),
                    native_output=None,
                )
                for t in theorems
            ]
        # batch failed or timed out: attribute per theorem (failures must be
        # exact, never shared across an innocent batch)
        return [self._check_single(t) for t in theorems]

    def _check_single(self, theorem: str) -> LeanVerdict:
        (exit0, output, elapsed_ms) = self._run_lean(theorem, "single")
        status: LeanStatus
        if exit0:
            status = "attested"
        elif output is not None and "interrupt" in output.lower():
            status = "timeout"
        else:
            status = "failed"
        return LeanVerdict(
            status=status,
            kernel_version=self.kernel_version,
            file_digest=kernel_hash(theorem),
            time_ms=elapsed_ms,
            native_output=None if exit0 else output,
        )

    def _run_lean(self, content: str, tag: str) -> tuple[bool, str | None, int]:
        """Compile `content` as one .lean file; returns (exit0, output, ms)."""
        with tempfile.NamedTemporaryFile(
            "w", suffix=f"-{tag}.lean", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = Path(f.name)
        try:
            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    [self.executable, path.name],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=self.env(),
                    timeout=self.check_timeout_s,
                    cwd=path.parent,
                )
            except subprocess.TimeoutExpired:
                return (
                    False,
                    f"lean compile exceeded the {self.check_timeout_s}s budget (interrupt)",
                    int((time.perf_counter() - start) * 1000),
                )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            output = (proc.stdout + proc.stderr).strip() or None
            return proc.returncode == 0, output, elapsed_ms
        finally:
            path.unlink(missing_ok=True)
