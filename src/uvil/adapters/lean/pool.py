"""Warm-backend pooling: persistent Pantograph REPL sessions (skip-if-absent).

Plain `lean file.lean` compilation pays the ~1-4s process cold start per
batch (discovery-pinned). The warm pool instead keeps persistent Pantograph
REPL processes alive and submits theorems over JSON lines - the master-plan
"programmatic checking" boundary.

**Skip-if-absent (cvc5 precedent):** the pool is enabled only when
`UVIL_PANTOGRAPH` points at a built REPL binary; without it
`PantographNotInstalled` is raised and the plain-lean path stays the exit
criterion (zero Pantograph dependency). A `.py` path is run under the
current interpreter - the scripted-stdio test seam (and a legit way to wrap
the REPL).

**Protocol v2 (M5; discovery-pinned on the wire against Pantograph 0.3.x @
`92d4818`, the built REPL in `lean/pool/`):**

- Launch: the REPL is started with the `Init` import argument - a bare REPL
  environment is EMPTY (no prelude; even `True` is unknown), while the
  generated twins are standalone `Init`-prelude files. The REPL prints a
  `ready.` banner line on stdout once initialized.
- Wire form: `{"cmd": <name>, "payload": {...}}` - JSON-mode args must live
  under `payload` (a bare `{"cmd", "expr"}` leaves the payload null and the
  command fails with "Exactly one of {expr, copyFrom}").
- Liveness: `stat` (its `{"nGoals":0}` echo carries NO version, so
  `LeanVerdict.kernel_version` is the pinned toolchain id, not an echo).
- Submission: `goal.start` takes a TERM - a full theorem source fails with
  "expected term" (pinned) - so the pool splits the generated
  `theorem <name> : <stmt> := by <body>` into statement term + tactic body:
  `goal.start{expr: <stmt>}` -> `stateId`, then
  `goal.tactic{stateId, tactic: <body>}`. Single-tactic bodies only (the
  generated-twin shape; multi-line bodies fail loud - use the plain-lean
  path).
- Success gates (all must hold): response carries `nextStateId`, `goals` is
  empty, `hasSorry` is false, `hasUnsafe` is false, and the final
  `goal.print` reports `rootHasSorry` false. A sorry-tainted proof is
  `failed`, never attested (kernel-attestation discipline; the wire probe
  confirmed `sorry` closes goals with `hasSorry=true`).
- Proof states: `goal.print{stateId, goals: true}` maps
  `GoalPrintResult.goals[].target.pp` to `LeanProofState.goals`; a v2
  `LeanProofState` carries its `stateId` in the opaque I5 payload.
- Resume: goal states are SESSION-LOCAL - `resume` validates the state in
  the same session (goal states stay addressable across tactics; the REPL's
  automatic mode needs no `goal.continue`, which requires `branch`/`goals`
  and refuses unresolved targets). Cross-session resume fails loud.

Per-session env isolation: every `submit` runs `goal.start` fresh, so no
cross-artifact state leaks between obligations. Partial proof states are
storable as opaque I5 payloads (`format="lean-proof-state"`) -
schema-conformant, ADR-0001-clean.
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

# v2 = the Pantograph 0.3.x `goal.*` protocol (see module docstring).
_PROTOCOL_VERSION = 2

# Launch import: the minimal prelude module (discovery-pinned: without it the
# REPL environment is empty).
INIT_IMPORT = "Init"

_SORRY_GATE_NOTE = "proof is sorry-tainted (hasSorry/rootHasSorry); never attested"

_PROTOCOL_NOTE = "protocol v2: Pantograph 0.3.x goal.* (pinned rev 92d4818)"


class PantographNotInstalled(RuntimeError):
    """UVIL_PANTOGRAPH is not set to a built REPL binary (skip-if-absent)."""


@dataclass
class LeanProofState:
    """A partial proof state: the theorem under proof, its session state id,
    and the remaining goals (pretty-printed) as reported by the REPL. Storable
    as I5 `payload={"format": "lean-proof-state", "inline": <json>}`."""

    theorem: str
    stateId: int | None = None
    goals: list[str] = field(default_factory=list)
    protocol_version: int = _PROTOCOL_VERSION

    def to_payload(self) -> str:
        import json as _json

        return _json.dumps(
            {
                "theorem": self.theorem,
                "stateId": self.stateId,
                "goals": self.goals,
                "protocol_version": self.protocol_version,
            },
            sort_keys=True,
        )

    @staticmethod
    def from_payload(inline: str) -> LeanProofState:
        data = json.loads(inline)
        if data.get("protocol_version") != _PROTOCOL_VERSION:
            raise ValueError(
                f"proof-state payload protocol mismatch: expected {_PROTOCOL_VERSION}, "
                f"got {data.get('protocol_version')!r}"
            )
        state_id = data.get("stateId")
        return LeanProofState(
            theorem=data["theorem"],
            stateId=state_id if isinstance(state_id, int) else None,
            goals=list(data["goals"]),
            protocol_version=data["protocol_version"],
        )


def session_command(binary: str) -> list[str]:
    """The subprocess command for the REPL binary, launched with the `Init`
    import (a bare environment is empty - discovery-pinned). A `.py` path
    runs under the current interpreter (the scripted-stdio test seam)."""
    if binary.endswith(".py"):
        return [sys.executable, binary, INIT_IMPORT]
    return [binary, INIT_IMPORT]


def split_theorem(theorem: str) -> tuple[str, str]:
    """Split `theorem <name> : <stmt> := by <body>` into (stmt, body).

    Fail loud on anything but the generated single-tactic shape: the wire
    probe pinned `goal.start` to terms, and `goal.tactic` to one tactic.
    """
    marker = " := by"
    idx = theorem.find(marker)
    if idx < 0 or not theorem.startswith("theorem "):
        raise ValueError(
            f"theorem source is not in the generated 'theorem n : stmt := by body' "
            f"shape: {theorem[:80]!r}"
        )
    decl = theorem[:idx]
    body = theorem[idx + len(marker) :].strip()
    sep = " : "
    sidx = decl.find(sep)
    if sidx < 0:
        raise ValueError(f"theorem source has no statement separator: {theorem[:80]!r}")
    stmt = decl[sidx + len(sep) :].strip()
    if "\n" in body:
        raise ValueError(
            "multi-tactic proof bodies are not supported by the warm pool "
            "(protocol v2: single-tactic goal.tactic); use the plain-lean path"
        )
    return stmt, body


class PantographSession:
    """One persistent REPL process; JSON-lines request/response (protocol v2)."""

    def __init__(self, command: list[str], start_timeout_s: float = 30.0) -> None:
        del start_timeout_s  # banner read is blocking; a wedged init dies on read
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
        self._state_id: int | None = None
        self._theorem: str | None = None
        self._setup()

    def _setup(self) -> None:
        """Consume the `ready.` banner, then probe liveness with `stat`."""
        line = self._read_line()
        if line.strip() != "ready.":
            self._closed = True
            raise RuntimeError(f"pantograph REPL did not announce readiness: {line[:200]!r}")
        response = self._request({"cmd": "stat", "payload": None})
        if not isinstance(response, dict):
            raise RuntimeError(f"pantograph REPL liveness probe failed: {response!r}")

    def _read_line(self) -> str:
        if self._closed or self._proc.stdout is None:
            raise RuntimeError("pantograph session is closed")
        line: str = self._proc.stdout.readline()
        if not line:
            self._closed = True
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"pantograph REPL died: {stderr[:500]}")
        return line

    def _request(
        self, payload: dict[str, object], timeout_s: float | None = None
    ) -> dict[str, object]:
        del timeout_s  # synchronous REPL: a wedged session surfaces on the next read
        if self._closed or self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("pantograph session is closed")
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(payload, sort_keys=True) + "\n")
        self._proc.stdin.flush()
        line = self._read_line()
        try:
            response: dict[str, object] = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"unparseable REPL response: {line[:200]!r}") from e
        return response

    # -- v2 proof flow -----------------------------------------------------------

    def start_proof(self, theorem: str) -> None:
        """Open a proof namespace: `goal.start` on the statement term."""
        stmt, _body = split_theorem(theorem)
        response = self._request({"cmd": "goal.start", "payload": {"expr": stmt}})
        if "error" in response:
            raise RuntimeError(f"goal.start failed: {response.get('desc', response)}")
        state_id = response.get("stateId")
        if not isinstance(state_id, int):
            raise RuntimeError(f"malformed goal.start response: {response!r}")
        self._state_id = state_id
        self._theorem = theorem

    def _tactic_response(self, body: str) -> dict[str, object]:
        if self._state_id is None:
            raise RuntimeError("no active proof namespace (call start_proof first)")
        response = self._request(
            {"cmd": "goal.tactic", "payload": {"stateId": self._state_id, "tactic": body}}
        )
        next_state = response.get("nextStateId")
        if isinstance(next_state, int):
            self._state_id = next_state
        return response

    def submit(self, theorem: str) -> LeanVerdict:
        """Check a full theorem in a fresh namespace (per-obligation isolation).

        Attestation gates (discovery-pinned): `nextStateId` present, `goals`
        empty, `hasSorry`/`hasUnsafe` false, final `rootHasSorry` false.
        Timeouts are enforced on the plain-lean compile path; a synchronous
        REPL has no cancel, so a wedged session surfaces as a died-REPL error
        on the next request."""
        start = time.perf_counter()

        def verdict(status: str, native_output: str | None) -> LeanVerdict:
            return LeanVerdict(
                status=status,  # type: ignore[arg-type]
                kernel_version=TOOLCHAIN_ID,
                file_digest=kernel_hash(theorem),
                time_ms=int((time.perf_counter() - start) * 1000),
                native_output=native_output,
            )

        try:
            self.start_proof(theorem)
        except ValueError as e:
            return verdict("failed", str(e))
        _stmt, body = split_theorem(theorem)
        response = self._tactic_response(body)
        if "error" in response or "nextStateId" not in response:
            messages = json.dumps(response.get("messages", response), sort_keys=True, default=str)
            return verdict("failed", messages)
        if response.get("hasSorry") or response.get("hasUnsafe"):
            return verdict("failed", f"{_SORRY_GATE_NOTE} ({_PROTOCOL_NOTE})")
        if response.get("goals"):
            return verdict("failed", f"proof incomplete: {response.get('goals')!r}")
        final = self._request(
            {
                "cmd": "goal.print",
                "payload": {"stateId": self._state_id, "goals": False},
            }
        )
        if final.get("rootHasSorry"):
            return verdict("failed", _SORRY_GATE_NOTE)
        return verdict("attested", None)

    def capture_proof_state(self) -> LeanProofState:
        """Snapshot the remaining goals of the active proof namespace."""
        if self._state_id is None or self._theorem is None:
            raise RuntimeError("no active proof namespace (protocol v2: submit first)")
        response = self._request(
            {"cmd": "goal.print", "payload": {"stateId": self._state_id, "goals": True}}
        )
        if "error" in response:
            raise RuntimeError(f"goal capture failed: {response.get('desc', response)}")
        raw_goals = response.get("goals", [])
        if not isinstance(raw_goals, list):
            raise RuntimeError(f"malformed goals payload: {raw_goals!r}")
        goals = []
        for g in raw_goals:
            if isinstance(g, dict) and isinstance(g.get("target"), dict):
                pp = g["target"].get("pp")
                goals.append(str(pp) if pp is not None else json.dumps(g, sort_keys=True))
            else:
                goals.append(str(g))
        return LeanProofState(theorem=self._theorem, stateId=self._state_id, goals=goals)

    def resume(self, state: LeanProofState) -> None:
        """Validate a captured proof state into this session.

        Protocol v2: goal states are session-local (addressable ids in the
        REPL's state map; automatic mode keeps them live across tactics).
        Resuming a state captured in a DIFFERENT session is impossible -
        fail loud rather than pretend."""
        if state.protocol_version != _PROTOCOL_VERSION:
            raise ValueError(
                f"proof-state protocol mismatch: expected {_PROTOCOL_VERSION}, "
                f"got {state.protocol_version}"
            )
        if self._state_id == state.stateId and self._theorem == state.theorem:
            response = self._request(
                {"cmd": "goal.print", "payload": {"stateId": state.stateId, "goals": False}}
            )
            if "error" in response:
                raise RuntimeError(f"resume failed: {response.get('desc', response)}")
            return
        raise RuntimeError(
            "proof state is session-local: it can only be resumed in the session "
            "that captured it (protocol v2)"
        )

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
