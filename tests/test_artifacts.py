from __future__ import annotations

import pytest

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
from uvil.artifacts import (
    artifact_id,
    artifact_type_of,
    canonical_bytes,
    content_hash,
    parse_artifact,
)

ALL_MAKERS = [
    make_intent,
    make_spec,
    make_program,
    make_obligation,
    lambda: make_proof("obl:x"),
    lambda: make_counterexample("obl:x"),
    lambda: make_diagnostic("obl:x"),
    lambda: make_run(["obl:x"]),
    lambda: make_translation("uvil:obligation@1:a", "uvil:obligation@1:b"),
]


def test_registry_has_nine_types() -> None:
    assert len(ALL_MAKERS) == 9


@pytest.mark.parametrize("maker", ALL_MAKERS)
def test_artifact_id_format(maker) -> None:
    model = maker()
    aid = artifact_id(model)
    parts = aid.split(":")
    assert len(parts) == 3 and parts[0] == "uvil" and "@" in parts[1]
    assert parts[1].split("@")[0] == model.uvil_type
    assert len(parts[2]) == 64


@pytest.mark.parametrize("maker", ALL_MAKERS)
def test_hash_deterministic(maker) -> None:
    model = maker()
    assert content_hash(model) == content_hash(model.model_copy())
    assert canonical_bytes(model) == canonical_bytes(model.model_copy())


@pytest.mark.parametrize("maker", ALL_MAKERS)
def test_canonical_bytes_is_minified_sorted_json(maker) -> None:
    import json

    raw = canonical_bytes(maker()).decode()
    reparsed = json.loads(raw)
    assert json.dumps(reparsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False) == raw


@pytest.mark.parametrize("maker", ALL_MAKERS)
def test_hash_changes_on_mutation(maker) -> None:
    model = maker()
    d = model.model_dump()
    str_field = next((k for k, v in d.items() if isinstance(v, str)), None)
    if str_field is None:
        assert content_hash(model) == content_hash(type(model).model_validate(d))
        return
    d[str_field] = d[str_field] + "x"
    changed = type(model).model_validate(d)
    assert content_hash(model) != content_hash(changed)


@pytest.mark.parametrize("maker", ALL_MAKERS)
def test_model_json_roundtrip(maker) -> None:
    model = maker()
    clone = type(model).model_validate_json(model.model_dump_json())
    assert content_hash(model) == content_hash(clone)
    assert artifact_id(model) == artifact_id(clone)


@pytest.mark.parametrize("maker", ALL_MAKERS)
def test_parse_artifact_envelope(maker) -> None:
    model = maker()
    envelope = {
        "uvil_type": model.uvil_type,
        "schema_version": model.schema_version,
        "artifact": model.model_dump(mode="json"),
    }
    parsed = parse_artifact(envelope)
    assert artifact_id(parsed) == artifact_id(model)
    assert artifact_type_of(artifact_id(parsed)) == model.uvil_type


def test_parse_artifact_rejects_wrong_type() -> None:
    model = make_intent()
    envelope = {
        "uvil_type": model.uvil_type,
        "schema_version": model.schema_version,
        "artifact": model.model_dump(mode="json"),
    }
    with pytest.raises(ValueError, match="expected artifact type"):
        parse_artifact(envelope, expected_type="obligation")


def test_artifact_type_of_rejects_malformed() -> None:
    with pytest.raises(ValueError, match="malformed artifact id"):
        artifact_type_of("not-an-id")
