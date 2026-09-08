"""uvil.schemas - generated JSON Schema for artifact types (uvil.<type>.schema.json)."""

from __future__ import annotations

from pathlib import Path

from .export import build_schema, export_schemas, schema_bytes

CHECKED_IN_DIR = Path(__file__).parent

__all__ = ["CHECKED_IN_DIR", "build_schema", "export_schemas", "schema_bytes"]
