"""uvil.artifacts - I1-I9 artifact models, core assertion language, canonical hashing."""

from __future__ import annotations

from .base import (
    Artifact,
    artifact_id,
    artifact_type_of,
    canonical_bytes,
    canonical_json_bytes,
    content_hash,
    parse_artifact,
    sha256_hex,
)
from .counterexample import Counterexample
from .diagnostic import Diagnostic
from .intent import Intent
from .obligation import Obligation, ObligationStatus
from .program import Program
from .proof import Proof
from .registry import artifact_types, get_artifact_class
from .run import Run
from .spec import Specification
from .terms import Term, to_smt
from .translation import SoundnessDiscipline, Translation

__all__ = [
    "Artifact",
    "Counterexample",
    "Diagnostic",
    "Intent",
    "Obligation",
    "ObligationStatus",
    "Program",
    "Proof",
    "Run",
    "SoundnessDiscipline",
    "Specification",
    "Term",
    "Translation",
    "artifact_id",
    "artifact_type_of",
    "artifact_types",
    "canonical_bytes",
    "canonical_json_bytes",
    "content_hash",
    "get_artifact_class",
    "parse_artifact",
    "sha256_hex",
    "to_smt",
]
