"""Content-addressed object store: filesystem CAS keyed by sha256."""

from __future__ import annotations

from pathlib import Path

from ..artifacts import Artifact, artifact_id, artifact_type_of, canonical_bytes, sha256_hex


class ContentStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.objects / digest[:2] / digest

    def put_bytes(self, data: bytes) -> str:
        digest = sha256_hex(data)
        path = self._path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return digest

    def get_bytes(self, digest: str) -> bytes:
        path = self._path(digest)
        if not path.exists():
            raise KeyError(f"object not in store: {digest}")
        data = path.read_bytes()
        if sha256_hex(data) != digest:
            raise ValueError(f"store corruption: digest mismatch for {digest}")
        return data

    def has(self, digest: str) -> bool:
        return self._path(digest).exists()

    def put_artifact(self, model: Artifact) -> str:
        aid = artifact_id(model)
        digest = aid.rsplit(":", 1)[-1]
        if not self.has(digest):
            self.put_bytes(canonical_bytes(model))
        return aid

    def get_artifact(self, aid: str) -> Artifact:
        from ..artifacts import get_artifact_class

        uvil_type = artifact_type_of(aid)
        digest = aid.rsplit(":", 1)[-1]
        data = self.get_bytes(digest)
        return get_artifact_class(uvil_type).model_validate_json(data)
