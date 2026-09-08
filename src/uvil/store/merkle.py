"""Merkle tree over artifact hashes, stored in the CAS.

Leaves are domain-separated artifact hashes; interior nodes hash their children.
The root commits to the full artifact set - the basis of the M5 incremental diff.
"""

from __future__ import annotations

from ..artifacts import sha256_hex


def _leaf_hash(artifact_hash: str) -> str:
    return sha256_hex(f"uvil-leaf:{artifact_hash}".encode())


def _node_hash(left: str, right: str) -> str:
    first, second = sorted((left, right))
    return sha256_hex(f"uvil-node:{first}:{second}".encode())


def _levels(artifact_hashes: list[str]) -> list[list[str]]:
    level = sorted(_leaf_hash(h) for h in artifact_hashes)
    levels: list[list[str]] = []
    while len(level) > 1:
        if len(level) % 2 == 1:
            level = [*level, level[-1]]
        levels.append(level)
        level = [_node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    levels.append(level)
    return levels


def merkle_root(artifact_hashes: list[str]) -> str:
    if not artifact_hashes:
        return sha256_hex(b"uvil-merkle:empty")
    levels = _levels(artifact_hashes)
    return levels[-1][0]


def merkle_branches(artifact_hashes: list[str], target: str) -> list[str]:
    """Audit path proving `target` is committed to by the root."""
    if target not in artifact_hashes:
        raise KeyError(f"{target!r} is not a leaf of this tree")
    levels = _levels(artifact_hashes)
    current = _leaf_hash(target)
    proof: list[str] = []
    for level in levels[:-1]:
        idx = level.index(current)
        sibling = level[idx ^ 1]
        proof.append(sibling)
        current = _node_hash(current, sibling)
    return proof


def merkle_verify(leaf_hash: str, root: str, branches: list[str]) -> bool:
    current = _leaf_hash(leaf_hash)
    for sibling in branches:
        current = _node_hash(current, sibling)
    return current == root
