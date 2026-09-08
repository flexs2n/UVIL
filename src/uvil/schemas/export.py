"""JSON Schema export for every artifact type: `uvil.<type>.schema.json`.

Schemas are versioned with the artifact `schema_version` (`@1`, frozen at M1 per
ADR 0001). The checked-in files under `src/uvil/schemas/` are regenerated with
`uvil schema --all --out src/uvil/schemas`; a test keeps them in lockstep.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..artifacts import artifact_types, get_artifact_class


def build_schema(uvil_type: str) -> dict[str, object]:
    cls = get_artifact_class(uvil_type)
    schema: dict[str, object] = cls.model_json_schema()
    schema["$id"] = f"https://uvil.dev/schemas/uvil.{uvil_type}.schema.json"
    schema["title"] = f"uvil.{uvil_type}@{cls.schema_version}"
    return schema


def export_schemas(out_dir: Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for uvil_type in artifact_types():
        path = out / f"uvil.{uvil_type}.schema.json"
        path.write_text(
            json.dumps(build_schema(uvil_type), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def schema_bytes(uvil_type: str) -> bytes:
    return json.dumps(build_schema(uvil_type), indent=2, sort_keys=True).encode("utf-8") + b"\n"
