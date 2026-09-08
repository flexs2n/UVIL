"""Registry of artifact types (I1-I9)."""

from __future__ import annotations

from .base import Artifact
from .counterexample import Counterexample
from .diagnostic import Diagnostic
from .intent import Intent
from .obligation import Obligation
from .program import Program
from .proof import Proof
from .run import Run
from .spec import Specification
from .translation import Translation

type ArtifactClass = type[Artifact]

_REGISTRY: dict[str, ArtifactClass] = {
    Intent.uvil_type: Intent,
    Specification.uvil_type: Specification,
    Program.uvil_type: Program,
    Obligation.uvil_type: Obligation,
    Proof.uvil_type: Proof,
    Counterexample.uvil_type: Counterexample,
    Diagnostic.uvil_type: Diagnostic,
    Run.uvil_type: Run,
    Translation.uvil_type: Translation,
}

assert len(_REGISTRY) == 9, "artifact registry must cover exactly I1-I9"


def get_artifact_class(uvil_type: str) -> ArtifactClass:
    try:
        return _REGISTRY[uvil_type]
    except KeyError:
        raise ValueError(
            f"unknown artifact type {uvil_type!r}; known: {sorted(_REGISTRY)}"
        ) from None


def artifact_types() -> list[str]:
    return sorted(_REGISTRY)


__all__ = [
    "Artifact",
    "ArtifactClass",
    "Counterexample",
    "Diagnostic",
    "Intent",
    "Obligation",
    "Program",
    "Proof",
    "Run",
    "Specification",
    "Translation",
    "artifact_types",
    "get_artifact_class",
]
