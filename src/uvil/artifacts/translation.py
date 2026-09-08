"""I9 - Translation: the bridge object.

`source_artifact → target_artifact` with AST-level mapping, a soundness discipline
from {kernel-checked, roundtrip-validated, shadow-validated, lossy, unverified}, and
residuals (assumptions added, proof fragments dropped, residual obligations emitted).
Only `kernel-checked` translations are admissible in guarantee-carrying mode (§5.5).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import Artifact

SoundnessDiscipline = Literal[
    "kernel-checked", "roundtrip-validated", "shadow-validated", "lossy", "unverified"
]


class Residuals(BaseModel):
    assumptions_added: list[str] = []
    dropped_fragments: list[str] = []
    residual_obligations: list[str] = []


class Translation(Artifact):
    uvil_type = "translation"

    source_artifact: str
    target_artifact: str
    source_kind: str
    target_kind: str
    mapping: list[dict[str, Any]] = []
    soundness_discipline: SoundnessDiscipline
    residuals: Residuals = Field(default_factory=Residuals)
    notes: str | None = None
