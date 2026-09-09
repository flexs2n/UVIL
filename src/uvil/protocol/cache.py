"""Verdict cache for the M5 incremental protocol.

The cache maps an obligation's *identity* (the M0 cache key from
`store/identity.py::obligation_identity`, additionally pinned to the backend,
its tool version, and the protocol version) to a reused `discharged` verdict.
Soundness rules, enforced by construction:

- Only `discharged` verdicts are ever stored (`put` rejects anything else):
  a refutation is cheap to re-derive and a non-discharge is not a reusable
  guarantee. `unknown`/`timeout` re-solve every time.
- The key pins backend + tool version + protocol version, so a solver upgrade
  or a protocol change invalidates cached verdicts (fail-safe: never
  stale-reused).
- A malformed cache file is a hard error (fail loud); a missing file is an
  empty cache.

The index is a JSON document at `<state>/verdict-cache.json` (not a CAS
artifact - it is reproducible scratch state, not evidence; the evidence of a
reuse is the Merkle diff recorded on the incremental result).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ..artifacts import canonical_json_bytes, sha256_hex

# Bump when the cache value shape or the reuse semantics change: old indexes
# stop matching (fail-safe re-solve) rather than being misread.
PROTOCOL_VERSION = 1

_INDEX_VERSION = 1


@dataclass(frozen=True)
class CacheEntry:
    """A reusable `discharged` verdict, with its provenance."""

    status: str  # always "discharged" (enforced by put)
    obligation_ref: str
    run_ref: str
    ledger_seq: int
    ts: str
    identity: str  # the obligation identity this entry was keyed by


def cache_key(identity: str, backend: str, tool_version: str) -> str:
    """The full cache key: identity + backend + tool pin + protocol version."""
    parts = {
        "identity": identity,
        "backend": backend,
        "tool_version": tool_version,
        "protocol_version": PROTOCOL_VERSION,
    }
    return sha256_hex(canonical_json_bytes(parts))


class VerdictCache:
    """JSON-backed discharged-verdict index inside a UVIL state directory."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, dict[str, object]] | None = None

    def _load(self) -> dict[str, dict[str, object]]:
        if self._data is None:
            if not self.path.exists():
                self._data = {}
            else:
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    raise ValueError(f"malformed verdict cache: {self.path}: {e}") from e
                if not isinstance(raw, dict) or "entries" not in raw:
                    raise ValueError(f"malformed verdict cache: {self.path}")
                if raw.get("version") != _INDEX_VERSION:
                    raise ValueError(
                        f"verdict cache version mismatch in {self.path}: "
                        f"expected {_INDEX_VERSION}, got {raw.get('version')!r}"
                    )
                entries = raw["entries"]
                if not isinstance(entries, dict):
                    raise ValueError(f"malformed verdict cache entries: {self.path}")
                self._data = entries
        return self._data

    def _flush(self, entries: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _INDEX_VERSION, "entries": entries}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._data = entries

    def get(self, identity: str, backend: str, tool_version: str) -> CacheEntry | None:
        """Look up a cached verdict; None on any miss (never a stale reuse)."""
        entry = self._load().get(cache_key(identity, backend, tool_version))
        if entry is None:
            return None
        return CacheEntry(
            status=str(entry["status"]),
            obligation_ref=str(entry["obligation_ref"]),
            run_ref=str(entry["run_ref"]),
            ledger_seq=cast(int, entry["ledger_seq"]),
            ts=str(entry["ts"]),
            identity=str(entry["identity"]),
        )

    def put(
        self,
        identity: str,
        backend: str,
        tool_version: str,
        *,
        obligation_ref: str,
        run_ref: str,
        ledger_seq: int,
        status: str,
    ) -> None:
        """Record a verdict. Only `discharged` is cacheable (fail loud)."""
        if status != "discharged":
            raise ValueError(
                f"only discharged verdicts are cacheable, got {status!r} "
                f"(obligation {obligation_ref})"
            )
        entries = self._load()
        entries[cache_key(identity, backend, tool_version)] = {
            "status": status,
            "obligation_ref": obligation_ref,
            "run_ref": run_ref,
            "ledger_seq": ledger_seq,
            "ts": datetime.now(UTC).isoformat(),
            "identity": identity,
        }
        self._flush(entries)

    def known_identities(self, incremental_since: int | None = None) -> set[str]:
        """Identities currently in the cache.

        With `incremental_since`, only entries whose ledger seq is
        `<= incremental_since` count as known (the "prior state" for the
        Merkle diff): later entries are treated as not yet existing.
        """
        out: set[str] = set()
        for entry in self._load().values():
            if incremental_since is not None and cast(int, entry["ledger_seq"]) > incremental_since:
                continue
            ident = entry.get("identity")
            if isinstance(ident, str):
                out.add(ident)
        return out
