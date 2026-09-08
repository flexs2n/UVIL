"""I3 - Program: source pointer + registered semantics model.

The semantics model maps source constructs into the shared theories and is itself
a versioned, citable artifact (see `uvil.semmodels`) - making library mismatch a
first-class, hashable object instead of silent implicit context.
"""

from __future__ import annotations

from typing import Any

from .base import Artifact


class Program(Artifact):
    uvil_type = "program"

    language: str
    source_ref: str
    symbol: str | None = None
    fragment: str | None = None
    semantics_model: str
    ast: dict[str, Any] | None = None
    intent_ref: str | None = None
    notes: str | None = None
