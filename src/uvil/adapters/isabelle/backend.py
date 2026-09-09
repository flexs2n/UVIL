"""Pinned Isabelle backend: session-build attestation of HOL theory files.

Attestation = exit-0 of `isabelle build -D <session dir>` on a batched theory
file (`theory ... imports Main begin ... end`) under the pinned bundle. Like
the Lean path, this is offline-verifiable: anyone with the pinned Isabelle
bundle can re-run the build on the stored bytes - no UVIL code, no network,
no solver (R1).

Fail-loud pins (ADR 0002 discipline; ADR 0005 documents the bundle pin):
- absent isabelle        -> `IsabelleNotInstalled` (tests self-skip, CLI skips)
- present-but-mismatched -> `IsabelleVersionMismatch` hard error

`UVIL_ISABELLE` overrides the executable location (cvc5 precedent). The
verdict->status mapping is total and fail-loud: `attested -> discharged`,
`failed -> open` (+ I7 unproved), `timeout -> open` (+ I7 timeout) - a failed
proof search NEVER refutes (it produces no counterexample) and never
discharges. `nitpick`/`quickcheck` counterexample oracles are NOT wired:
counterexamples only become I6 when a live oracle yields a genuine model
(ADR 0005 records the candidate).
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
from .encode import ISABELLE_BATCH_SIZE, theory_file

# Hard pin per docs/decisions/0002-tool-pinning.md: the current stable
# release bundle (self-contained native Windows build).
PINNED_ISABELLE = "Isabelle2025"
ISABELLE_VERSION_ID = PINNED_ISABELLE  # the recorded version id in kernel hashes

ISABELLE_ENV_VAR = "UVIL_ISABELLE"

IsabelleStatus = Literal["attested", "failed", "timeout"]


class IsabelleNotInstalled(RuntimeError):
    """isabelle is not available on this machine (skip-if-absent paths)."""


class IsabelleVersionMismatch(RuntimeError):
    """A present-but-unpinned Isabelle bundle - hard error, never a warning."""


@dataclass(frozen=True)
class IsabelleVerdict:
    status: IsabelleStatus
    isabelle_version: str
    theory_digest: str
    time_ms: int | None
    native_output: str | None


def isabelle_status(verdict: IsabelleVerdict) -> ObligationStatus:
    """The single verdict->status mapping point. Failed/timeout never discharge
    and never refute: a proof-search failure produces no counterexample."""
    mapping: dict[IsabelleStatus, ObligationStatus] = {
        "attested": "discharged",
        "failed": "open",
        "timeout": "open",
    }
    return mapping[verdict.status]


def theory_bytes(content: str) -> bytes:
    """The exact .thy file bytes (the stored payload is byte-identical to
    this, which is what makes offline replay possible)."""
    return content.encode("utf-8")


def kernel_hash(theory_content: str) -> str:
    """sha256(theory-file bytes + Isabelle version id) - the recorded
    attestation over the batched theory file."""
    h = hashlib.sha256()
    h.update(theory_bytes(theory_content))
    h.update(ISABELLE_VERSION_ID.encode("utf-8"))
    return h.hexdigest()


def find_isabelle() -> str:
    """Locate an isabelle executable (PATH first, then `UVIL_ISABELLE`)."""
    override = os.environ.get(ISABELLE_ENV_VAR)
    if override:
        if Path(override).exists():
            return override
        raise IsabelleNotInstalled(
            f"{ISABELLE_ENV_VAR} points at a missing executable: {override} "
            f"(pin: {PINNED_ISABELLE})"
        )
    found = shutil.which("isabelle")
    if found:
        return found
    raise IsabelleNotInstalled(
        f"isabelle is not installed (set {ISABELLE_ENV_VAR} to the pinned "
        f"{PINNED_ISABELLE} bundle's bin/isabelle)"
    )


class IsabelleBackend:
    name = "isabelle-hol"

    def __init__(self, check_timeout_s: float | None = None) -> None:
        self.executable = find_isabelle()
        self.check_timeout_s = check_timeout_s
        self.isabelle_version = self._verify_version()

    def _verify_version(self) -> str:
        proc = subprocess.run(
            [self.executable, "version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not output:
            raise IsabelleVersionMismatch(f"cannot determine Isabelle version from: {output!r}")
        version = output.splitlines()[-1].strip()
        if not version.startswith("Isabelle"):
            raise IsabelleVersionMismatch(f"cannot determine Isabelle version from: {output!r}")
        if version != PINNED_ISABELLE:
            raise IsabelleVersionMismatch(
                f"Isabelle {version} is installed but the pin requires {PINNED_ISABELLE} "
                "(docs/decisions/0002-tool-pinning.md)"
            )
        return version

    def check_batch(self, theorems: list[str]) -> list[IsabelleVerdict]:
        """Attest theorems in batched theory files; returns one verdict per
        theorem, aligned with the input. A failing batch is re-run per theorem
        so failures attribute exactly."""
        verdicts: list[IsabelleVerdict] = []
        for start in range(0, len(theorems), ISABELLE_BATCH_SIZE):
            chunk = theorems[start : start + ISABELLE_BATCH_SIZE]
            verdicts.extend(self._check_chunk(chunk))
        return verdicts

    def _check_chunk(self, theorems: list[str]) -> list[IsabelleVerdict]:
        theory = theory_file(theorems, self._theory_name(theorems))
        (exit0, _, elapsed_ms) = self._run_build(theory)
        if exit0:
            digest = kernel_hash(theory)
            return [
                IsabelleVerdict(
                    status="attested",
                    isabelle_version=self.isabelle_version,
                    theory_digest=digest,
                    time_ms=elapsed_ms // len(theorems),
                    native_output=None,
                )
                for _ in theorems
            ]
        # batch failed or timed out: attribute per theorem (failures must be
        # exact, never shared across an innocent batch)
        return [self._check_single(t) for t in theorems]

    def _check_single(self, theorem: str) -> IsabelleVerdict:
        theory = theory_file([theorem], self._theory_name([theorem]))
        (exit0, output, elapsed_ms) = self._run_build(theory)
        status: IsabelleStatus
        if exit0:
            status = "attested"
        elif output is not None and "timeout" in output.lower():
            status = "timeout"
        else:
            status = "failed"
        return IsabelleVerdict(
            status=status,
            isabelle_version=self.isabelle_version,
            theory_digest=kernel_hash(theory),
            time_ms=elapsed_ms,
            native_output=None if exit0 else output,
        )

    @staticmethod
    def _theory_name(theorems: list[str]) -> str:
        import hashlib

        digest = hashlib.sha256("\n".join(theorems).encode("utf-8")).hexdigest()[:8]
        return f"Uvil_Obligations_{digest}"

    def _run_build(self, theory_content: str) -> tuple[bool, str | None, int]:
        """Run `isabelle build -D <dir>` on a one-theory session; returns
        (exit0, output, ms). The session dir carries a ROOT pinning the
        theory to HOL (the shared-theory fragment needs nothing more)."""
        theory_name = self._theory_name_from(theory_content)
        with tempfile.TemporaryDirectory(prefix="uvil-isabelle-") as tmp:
            workdir = Path(tmp)
            (workdir / "ROOT").write_text(
                f"session Uvil_{theory_name} = HOL +\n  theories\n    {theory_name}\n",
                encoding="utf-8",
                newline="\n",
            )
            (workdir / f"{theory_name}.thy").write_text(
                theory_content, encoding="utf-8", newline="\n"
            )
            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    [self.executable, "build", "-D", ".", f"Uvil_{theory_name}"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.check_timeout_s,
                    cwd=workdir,
                )
            except subprocess.TimeoutExpired:
                return (
                    False,
                    f"isabelle build exceeded the {self.check_timeout_s}s budget",
                    int((time.perf_counter() - start) * 1000),
                )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            output = (proc.stdout + proc.stderr).strip() or None
            return proc.returncode == 0, output, elapsed_ms

    @staticmethod
    def _theory_name_from(theory_content: str) -> str:
        for line in theory_content.splitlines():
            if line.startswith("theory "):
                return line.removeprefix("theory ").strip()
        raise ValueError(f"malformed theory file: {theory_content!r:.80}")
