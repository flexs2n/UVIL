"""Canonical serialization, content addressing, and the artifact base class.

Canonical form is JCS-style: UTF-8 JSON, sorted keys, no insignificant whitespace
(ADR 0001). `artifact_id = "uvil:<type>@<version>:<hash>"` where hash is the
SHA-256 of the canonical bytes of the artifact model.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

type CanonicalData = Mapping[str, object]


def canonical_json_bytes(data: CanonicalData) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Artifact(BaseModel):
    """Base class for all UVIL artifacts (I1-I9)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uvil_type: ClassVar[str]
    schema_version: ClassVar[str] = "1"


def canonical_bytes(model: Artifact) -> bytes:
    return canonical_json_bytes(model.model_dump(mode="json"))


def content_hash(model: Artifact) -> str:
    return sha256_hex(canonical_bytes(model))


def artifact_id(model: Artifact) -> str:
    return f"uvil:{model.uvil_type}@{model.schema_version}:{content_hash(model)}"


def artifact_type_of(artifact_id_str: str) -> str:
    parts = artifact_id_str.split(":")
    if len(parts) != 3 or parts[0] != "uvil" or "@" not in parts[1]:
        raise ValueError(f"malformed artifact id: {artifact_id_str!r}")
    return parts[1].split("@", 1)[0]


def parse_artifact(data: CanonicalData, expected_type: str | None = None) -> Artifact:
    """Parse an artifact envelope `{"uvil_type", "schema_version", "artifact"}`."""
    from .registry import get_artifact_class

    uvil_type = data.get("uvil_type")
    if not isinstance(uvil_type, str):
        raise ValueError("artifact envelope requires a string 'uvil_type'")
    if expected_type is not None and uvil_type != expected_type:
        raise ValueError(f"expected artifact type {expected_type!r}, got {uvil_type!r}")
    payload = data.get("artifact")
    if not isinstance(payload, dict):
        raise ValueError("artifact envelope requires an object 'artifact'")
    return get_artifact_class(uvil_type).model_validate(payload)
