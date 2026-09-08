"""I8 - Verification Run: full provenance record of a checking session.

Tool, version, flags, per-obligation verdicts, resource stats, kernel attestations.
Machine-diffable; the unit of incremental re-verification (M5 consumes these).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base import Artifact
from .obligation import ObligationStatus


class ToolDescriptor(BaseModel):
    name: str
    version: str
    flags: list[str] = []


class Verdict(BaseModel):
    obligation_ref: str
    status: ObligationStatus
    time_ms: int | None = None
    note: str | None = None


class KernelAttestation(BaseModel):
    backend: str
    kernel_hash: str
    checked: bool = False


class Run(Artifact):
    uvil_type = "run"

    tool: ToolDescriptor
    config: dict[str, Any] = {}
    verdicts: list[Verdict] = Field(min_length=1)
    resource_stats: dict[str, Any] = {}
    kernel_attestations: list[KernelAttestation] = []
    parent_run: str | None = None
    ledger_seq: int | None = None
