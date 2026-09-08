"""I1 - Intent: natural-language requirement(s) + structured metadata.

Not formal. Exists so every formal artifact is traceable to an informal source;
its hash participates in all downstream provenance. Carries no semantics.
"""

from __future__ import annotations

from pydantic import Field

from .base import Artifact


class Intent(Artifact):
    uvil_type = "intent"

    title: str
    requirements: list[str] = Field(min_length=1)
    constraints: list[str] = []
    forbidden_behaviors: list[str] = []
    priority: int | None = None
    refines: list[str] = []
    notes: str | None = None
