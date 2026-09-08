"""Append-only guarantee ledger (draft §5.5).

Every entry records artifact refs, a guarantee class G0-G4, kernel/tool
attestation, and an optional signature. Entries are hash-chained: each
`entry_hash` commits to the entry body and the previous `entry_hash`, making the
journal tamper-evident. Signing hooks (ed25519) are pluggable; the field exists
from day one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..artifacts import sha256_hex

GUARANTEE_CLASSES = ("G0", "G1", "G2", "G3", "G4")


class Attestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    version: str | None = None
    kernel_hash: str | None = None
    detail: str | None = None


class LedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int
    ts: str
    artifact_refs: list[str] = Field(min_length=1)
    guarantee_class: str
    attestation: Attestation | None = None
    signature: str | None = None
    prev_hash: str | None = None
    entry_hash: str


def compute_entry_hash(
    seq: int,
    ts: str,
    artifact_refs: list[str],
    guarantee_class: str,
    attestation: Attestation | None,
    signature: str | None,
    prev_hash: str | None,
) -> str:
    body = {
        "seq": seq,
        "ts": ts,
        "artifact_refs": sorted(artifact_refs),
        "guarantee_class": guarantee_class,
        "attestation": attestation.model_dump(mode="json") if attestation else None,
        "signature": signature,
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return sha256_hex(canonical)


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        out = []
        for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                out.append(LedgerEntry.model_validate(json.loads(line)))
            except Exception as e:
                raise ValueError(f"malformed ledger entry at line {i + 1}: {e}") from e
        return out

    def append(
        self,
        artifact_refs: list[str],
        guarantee_class: str,
        attestation: Attestation | None = None,
        signature: str | None = None,
        ts: str | None = None,
    ) -> LedgerEntry:
        if guarantee_class not in GUARANTEE_CLASSES:
            raise ValueError(
                f"guarantee class must be one of {GUARANTEE_CLASSES}, got {guarantee_class!r}"
            )
        if not artifact_refs:
            raise ValueError("ledger entries must reference at least one artifact")
        existing = self.entries()
        prev_hash = existing[-1].entry_hash if existing else None
        seq = len(existing) + 1
        ts = ts or datetime.now(UTC).isoformat()
        entry_hash = compute_entry_hash(
            seq, ts, artifact_refs, guarantee_class, attestation, signature, prev_hash
        )
        entry = LedgerEntry(
            seq=seq,
            ts=ts,
            artifact_refs=artifact_refs,
            guarantee_class=guarantee_class,
            attestation=attestation,
            signature=signature,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")
        return entry

    def verify(self) -> list[str]:
        """Recompute the hash chain. Returns list of defects; empty means intact."""
        defects: list[str] = []
        prev_hash: str | None = None
        for i, entry in enumerate(self.entries()):
            if entry.seq != i + 1:
                defects.append(f"entry {i + 1}: non-monotonic seq {entry.seq}")
            if entry.prev_hash != prev_hash:
                defects.append(f"entry {entry.seq}: broken prev_hash link")
            recomputed = compute_entry_hash(
                entry.seq,
                entry.ts,
                entry.artifact_refs,
                entry.guarantee_class,
                entry.attestation,
                entry.signature,
                entry.prev_hash,
            )
            if recomputed != entry.entry_hash:
                defects.append(f"entry {entry.seq}: entry_hash mismatch (tampered)")
            prev_hash = entry.entry_hash
        return defects

    def diff(self, other: Ledger) -> dict[str, list[str]]:
        """Machine-diffable comparison of two journals by entry content.

        Entries are keyed by `(guarantee_class, artifact_refs)` - timestamps and
        signatures are intentionally excluded so that identical guarantees
        recorded in different sessions diff as equal.
        """

        def key(e: LedgerEntry) -> str:
            return f"{e.guarantee_class}:" + ",".join(sorted(e.artifact_refs))

        a = {key(e) for e in self.entries()}
        b = {key(e) for e in other.entries()}
        return {
            "only_in_self": sorted(a - b),
            "only_in_other": sorted(b - a),
        }
