"""Warm-backend pooling: persistent Pantograph REPL sessions (skip-if-absent).

Plain `lean file.lean` compilation pays the ~1-4s process cold start per
batch (discovery-pinned). The warm pool instead keeps persistent Pantograph
REPL processes alive and submits theorems over JSON lines - the master-plan
"programmatic checking" boundary.

**Skip-if-absent (cvc5 precedent):** the pool is enabled only when
`UVIL_PANTOGRAPH` points at a built `pantograph-repl` binary; without it
`PantographNotInstalled` is raised and the plain-lean path stays the exit
criterion (zero Pantograph dependency). A `.py` path is run under the
current interpreter - the scripted-stdio test seam (and a legit way to wrap
the REPL).

Per-session env isolation: every `submit` opens a fresh proof namespace
(`proof_start`), so no cross-artifact state can leak between obligations.
Partial proof states (`goals` -> `LeanProofState`) are storable as opaque I5
payloads (`format="lean-proof-state"`) - schema-conformant, ADR-0001-clean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

from ...artifacts import sha256_hex
from .backend import TOOLCHAIN_ID, LeanVerdict, kernel_hash

PANTOGRAPH_ENV_VAR = "UVIL_PANTOGRAPH"

# Wire protocol (pinned to the Pantograph REPL): JSON lines in, JSON lines
# out; every request carries a `cmd`; every response carries `ok` plus either
# payload keys or `errors`.
_PROTOCOL_VERSION = 1


class PantographNotInstalled(RuntimeError):
    """UVIL_PANTOGRAPH is not set to a built REPL binary (skip-if-absent)."""


@dataclass
class LeanProofState:
    """A partial proof state: the theorem under proof and the remaining goals
    as reported by the REPL. Storable as I5
    `payload={"format": "lean-proof-state", "inline": <json>}`."""

    theorem: str
    goals: list[str] = field(default_factory=list)
    protocol_version: int = _PROTOCOL_VERSION

    def to_payload(self) -> str:
        import json as _json

        return _json.dumps(
            {
                "theorem": self.theorem,
                "goals": self.goals,
                "protocol_version": self.protocol_version,
            },
            sort_keys=True,
        )

    @staticmethod
    def from_payload(inline: str) -> LeanProofState:
        data = json.loads(inline)
        return LeanProofState(
            theorem=data["theorem"],
            goals=list(data["goals"]),
            protocol_version=data["protocol_version"],
        )


def session_command(binary: str) -> list[str]:
    """The subprocess command for the REPL binary. A `.py` path runs under
    the current interpreter (the scripted-stdio test seam)."""
    if binary.endswith(".py"):
        return [sys.executable, binary]
    return [binary]


class PantographSession:
    """One persistent REPL process; JSON-lines request/response."""

    def __init__(self, command: list[str], start_timeout_s: float = 30.0) -> None:
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._command = list(command)
        self._closed = False
        self._setup(start_timeout_s)

    def _setup(self, timeout_s: float) -> None:
        response = self._request({"cmd": "setup", "toolchain": TOOLCHAIN_ID}, timeout_s)
        if not response.get("ok"):
            raise RuntimeError(f"pantograph REPL setup failed: {response.get('errors', response)}")

    def _request(
        self, payload: dict[str, object], timeout_s: float | None = None
    ) -> dict[str, object]:
        if self._closed or self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("pantograph session is closed")
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(payload, sort_keys=True) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            self._closed = True
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"pantograph REPL died: {stderr[:500]}")
        try:
            response: dict[str, object] = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"unparseable REPL response: {line[:200]!r}") from e
        return response

    def submit(self, theorem: str) -> LeanVerdict:
        """Check a full theorem in a fresh namespace (per-obligation isolation).

        Timeouts are enforced on the plain-lean compile path; a synchronous
        REPL has no cancel, so a wedged session surfaces as a died-REPL error
        on the next request."""
        start = time.perf_counter()
        response = self._request({"cmd": "proof_start", "expr": theorem})
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        kernel_version = str(response.get("kernel_version", "pantograph"))
        if response.get("ok"):
            return LeanVerdict(
                status="attested",
                kernel_version=kernel_version,
                file_digest=kernel_hash(theorem),
                time_ms=elapsed_ms,
                native_output=None,
            )
        errors = response.get("errors", response)
        return LeanVerdict(
            status="failed",
            kernel_version=kernel_version,
            file_digest=kernel_hash(theorem),
            time_ms=elapsed_ms,
            native_output=json.dumps(errors, sort_keys=True, default=str),
        )

    def capture_proof_state(self) -> LeanProofState:
        """Snapshot the remaining goals of the current proof namespace."""
        response = self._request({"cmd": "goals"})
        if not response.get("ok"):
            raise RuntimeError(f"goal capture failed: {response.get('errors', response)}")
        goals = response.get("goals", [])
        if not isinstance(goals, list):
            raise RuntimeError(f"malformed goals payload: {goals!r}")
        theorem = response.get("theorem", "")
        if not isinstance(theorem, str):
            raise RuntimeError(f"malformed theorem field: {theorem!r}")
        return LeanProofState(theorem=theorem, goals=[str(g) for g in goals])

    def resume(self, state: LeanProofState) -> None:
        """Restore a captured partial proof state into this session."""
        response = self._request(
            {
                "cmd": "proof_resume",
                "expr": state.theorem,
                "goals": state.goals,
                "protocol_version": state.protocol_version,
            }
        )
        if not response.get("ok"):
            raise RuntimeError(f"proof resume failed: {response.get('errors', response)}")

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait(timeout=10)

    def __enter__(self) -> PantographSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class LeanSessionPool:
    """A pool of persistent REPL sessions for warm checking."""

    def __init__(self, binary: str | None = None, size: int = 1) -> None:
        resolved = binary or os.environ.get(PANTOGRAPH_ENV_VAR)
        if not resolved:
            raise PantographNotInstalled(
                f"the warm pool is optional: set {PANTOGRAPH_ENV_VAR} to a built "
                "pantograph-repl binary (the exit criterion needs only plain lean)"
            )
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._command = session_command(resolved)
        self._sessions: list[PantographSession] = []
        self.size = size

    def _acquire(self) -> PantographSession:
        if self._sessions:
            return self._sessions.pop()
        return PantographSession(self._command)

    def _release(self, session: PantographSession) -> None:
        if len(self._sessions) < self.size:
            self._sessions.append(session)
        else:
            session.close()

    def submit(
        self, theorem: str, proof: str | None = None, timeout_s: float | None = None
    ) -> LeanVerdict:
        """Check one theorem on a pooled session; the session returns to the
        pool with a fresh namespace (isolation between obligations)."""
        del proof, timeout_s  # the theorem file is self-contained (`by omega`)
        session = self._acquire()
        try:
            return session.submit(theorem)
        finally:
            self._release(session)

    def capture_proof_state(self) -> LeanProofState:
        session = self._acquire()
        try:
            return session.capture_proof_state()
        finally:
            self._release(session)

    def resume(self, state: LeanProofState) -> None:
        session = self._acquire()
        try:
            session.resume(state)
        finally:
            self._release(session)

    def close(self) -> None:
        for session in self._sessions:
            session.close()
        self._sessions.clear()

    def __enter__(self) -> LeanSessionPool:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def state_payload_digest(state: LeanProofState) -> str:
    """Content hash for storing a proof state as an opaque I5 payload."""
    return sha256_hex(state.to_payload().encode("utf-8"))
