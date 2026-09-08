"""I5 - Proof / Certificate: opaque-by-default payload + checker descriptor.

For SMT-class backends, standard certificates (DRAT/LRAT, Alethe, LFSC) are adopted
as payload profiles. For ITPs, the native proof term is the artifact, stored with
its kernel hash. UVIL never re-verifies a kernel's work - it records and re-dispatches (R1).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .base import Artifact


class BackendDescriptor(BaseModel):
    name: str
    version: str
    kernel_hash: str | None = None


class ProofPayload(BaseModel):
    format: str
    location: str | None = None
    inline: str | None = None
    metadata: dict[str, Any] = {}


class Checker(BaseModel):
    entry: str
    independent: bool = False
    version: str | None = None


class Proof(Artifact):
    uvil_type = "proof"

    obligation_ref: str
    backend: BackendDescriptor
    payload: ProofPayload
    checker: Checker
