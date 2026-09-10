"""Semantics-model registry tests (the M5 Aeneas seed included)."""

from __future__ import annotations

import pytest

from uvil.semmodels.registry import (
    AENEAS_FUNCTIONAL_V1,
    DEFAULT_REGISTRY,
    ESBMC_GOTO_V1,
    STRATA_CORE_V1,
    WHY3_MEMORY_V1,
    SemanticsModelEntry,
)


def test_default_registry_contains_all_registered_models() -> None:
    models = {m.model_id for m in DEFAULT_REGISTRY.list()}
    assert models >= {
        WHY3_MEMORY_V1.model_id,
        ESBMC_GOTO_V1.model_id,
        STRATA_CORE_V1.model_id,
        AENEAS_FUNCTIONAL_V1.model_id,
    }


def test_aeneas_seed_is_registry_only() -> None:
    entry = DEFAULT_REGISTRY.get("model:aeneas-functional.v1")
    assert entry is AENEAS_FUNCTIONAL_V1
    assert entry.name == "aeneas-functional"
    assert entry.citation is not None and "Aeneas" in entry.citation
    assert entry.profiles == ("uvil.rust@1",)
    # registry-only seed: no adapter consumes it (no import path references it)
    assert "functional translation" in entry.description


def test_model_id_prefix_enforced() -> None:
    with pytest.raises(ValueError, match="model:"):
        SemanticsModelEntry(
            model_id="aeneas-functional.v1",
            name="aeneas-functional",
            version="v1",
            description="missing prefix",
        )


def test_registry_rejects_duplicate_ids() -> None:
    registry = DEFAULT_REGISTRY
    with pytest.raises(ValueError, match="already registered"):
        registry.register(WHY3_MEMORY_V1)


def test_unknown_model_lookup_fails_loud() -> None:
    with pytest.raises(KeyError, match="unknown semantics model"):
        DEFAULT_REGISTRY.get("model:does-not-exist.v1")
