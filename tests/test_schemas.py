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


# M2 schema-freeze guard (ADR 0001): the nine checked-in schema files must stay
# byte-identical to the M1 release (de740eb) - renderers, shadow evaluation, and
# the round-trip service consume them as-is. Any change here is a schema-break
# and must fail loudly, even if the models were re-exported consistently.
M1_SCHEMA_SHA256: dict[str, str] = {
    "counterexample": "e697a01e3bad50ab3afb1e76040bdea6d897f938baa5dbeb95800fffa0fd4afc",
    "diagnostic": "ece82434e35f85ac00fba98656d98376d9fe6679f03d821f21dca2a26fa107c6",
    "intent": "f17814a32d1f8d7039afa260dce223873af2ae848d015a465d7091cc002ca72e",
    "obligation": "5ae76b32e7ec258827ba0307286eb117aa6de08d7cac1e0253bcd879d3e53a9c",
    "program": "8a49fda4e414c289e580a91a90e1c09697e175fbe3323c78e1c68565a094a5fe",
    "proof": "da29ef102303a900029c8c823f7622005ea8a7b49cb5894dd0557ef330fd15a6",
    "run": "a6486182ea5cccc0ea0a7f83d41d97a48712474e7813cd7ac4d7e59552682471",
    "specification": "f8944a28a4da2fc6acdcf3375088befa433e00d2e189dc8fc920e13515ff4430",
    "translation": "60b0f8b7b12bd34adf78a8433b504608bdf6005bc9f8851070e89627e96c6a72",
}


def test_checked_in_schemas_byte_identical_to_m1() -> None:
    import hashlib

    assert set(M1_SCHEMA_SHA256) == set(artifact_types())
    for uvil_type, frozen in M1_SCHEMA_SHA256.items():
        path = CHECKED_IN_DIR / f"uvil.{uvil_type}.schema.json"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == frozen, f"{path.name} drifted from the M1 schema freeze (ADR 0001)"
