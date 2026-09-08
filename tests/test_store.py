from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.fixtures import make_obligation
from uvil.artifacts import artifact_id, canonical_bytes
from uvil.store import (
    ContentStore,
    merkle_branches,
    merkle_root,
    merkle_verify,
    obligation_identity,
)


@pytest.fixture
def store(tmp_path) -> ContentStore:
    return ContentStore(tmp_path / "store")


def test_put_get_roundtrip_reproduces_hash(store: ContentStore) -> None:
    model = make_obligation()
    aid = store.put_artifact(model)
    fetched = store.get_artifact(aid)
    assert artifact_id(fetched) == aid
    assert canonical_bytes(fetched) == canonical_bytes(model)


def test_put_is_idempotent(store: ContentStore) -> None:
    model = make_obligation()
    aid1 = store.put_artifact(model)
    aid2 = store.put_artifact(model)
    assert aid1 == aid2


def test_get_missing_raises(store: ContentStore) -> None:
    with pytest.raises(KeyError):
        store.get_artifact("uvil:obligation@1:" + "0" * 64)


def test_corruption_detected(store: ContentStore) -> None:
    model = make_obligation()
    aid = store.put_artifact(model)
    digest = aid.rsplit(":", 1)[-1]
    path = store.objects / digest[:2] / digest
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="corruption"):
        store.get_artifact(aid)


def test_merkle_root_deterministic_and_order_insensitive() -> None:
    hashes = [f"{i:064x}" for i in range(7)]
    assert merkle_root(hashes) == merkle_root(list(reversed(hashes)))
    assert merkle_root([]) == merkle_root([])


def test_merkle_root_detects_tamper() -> None:
    hashes = [f"{i:064x}" for i in range(7)]
    tampered = hashes.copy()
    tampered[3] = "f" * 64
    assert merkle_root(hashes) != merkle_root(tampered)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 8, 9])
def test_merkle_audit_paths(n: int) -> None:
    hashes = [f"{i:064x}" for i in range(n)]
    root = merkle_root(hashes)
    for h in hashes:
        proof = merkle_branches(hashes, h)
        assert merkle_verify(h, root, proof)


def test_merkle_rejects_non_leaf() -> None:
    with pytest.raises(KeyError):
        merkle_branches(["a" * 64], "b" * 64)


def test_obligation_identity_stability() -> None:
    a = obligation_identity(
        spec="spec:cap",
        semantics_model="model:why3-memory.v1",
        program_fragment="push",
        profile_version="1",
    )
    b = obligation_identity(
        spec="spec:cap",
        semantics_model="model:why3-memory.v1",
        program_fragment="push",
        profile_version="1",
    )
    c = obligation_identity(
        spec="spec:cap",
        semantics_model="model:why3-memory.v1",
        program_fragment="push",
        profile_version="2",
    )
    assert a == b and a != c and a.startswith("oblid:")


@given(st.integers(min_value=0, max_value=10**9), st.integers(min_value=0, max_value=10**9))
def test_obligation_hash_injective_enough(a: int, b: int) -> None:
    i1 = obligation_identity(
        spec=f"s{a}", semantics_model="m", program_fragment="p", profile_version="1"
    )
    i2 = obligation_identity(
        spec=f"s{b}", semantics_model="m", program_fragment="p", profile_version="1"
    )
    assert (i1 == i2) == (a == b)
