from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.fixtures import (
    make_counterexample,
    make_diagnostic,
    make_intent,
    make_obligation,
    make_program,
    make_proof,
    make_run,
    make_spec,
    make_translation,
)
from uvil.artifacts import artifact_types
from uvil.schemas import CHECKED_IN_DIR, build_schema, export_schemas, schema_bytes

ALL_MAKERS = {
    "intent": make_intent,
    "specification": make_spec,
    "program": make_program,
    "obligation": make_obligation,
    "proof": lambda: make_proof("obl:x"),
    "counterexample": lambda: make_counterexample("obl:x"),
    "diagnostic": lambda: make_diagnostic("obl:x"),
    "run": lambda: make_run(["obl:x"]),
    "translation": lambda: make_translation("uvil:obligation@1:a", "uvil:obligation@1:b"),
}


def test_nine_schema_types() -> None:
    assert artifact_types() == sorted(ALL_MAKERS)


def test_checked_in_schemas_exist() -> None:
    for uvil_type in artifact_types():
        path = CHECKED_IN_DIR / f"uvil.{uvil_type}.schema.json"
        assert path.exists(), f"missing checked-in schema: {path}"
        assert json.loads(path.read_text(encoding="utf-8")) == build_schema(uvil_type)


def test_export_schemas_roundtrip(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    assert len(written) == 9
    for uvil_type in artifact_types():
        raw = (tmp_path / f"uvil.{uvil_type}.schema.json").read_text(encoding="utf-8")
        assert raw == schema_bytes(uvil_type).decode()


@pytest.mark.parametrize("maker", ALL_MAKERS.values(), ids=ALL_MAKERS)
def test_fixtures_validate_against_exported_schemas(maker) -> None:
    model = maker()
    schema = build_schema(model.uvil_type)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(model.model_dump(mode="json")))
    assert not errors, [e.message for e in errors]


def test_schemas_carry_version_in_title() -> None:
    for uvil_type in artifact_types():
        assert build_schema(uvil_type)["title"].endswith("@1")
