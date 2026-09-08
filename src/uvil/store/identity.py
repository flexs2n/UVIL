"""Obligation identity - the M5 incremental-protocol cache key.

`identity = sha256(canonical(spec, semantics_model, program_fragment, profile_version))`
(draft §5.6). Getting canonicalization right first matters: changing it later
invalidates all corpora.
"""

from __future__ import annotations

from ..artifacts.base import canonical_json_bytes, sha256_hex


def obligation_identity(
    spec: str,
    semantics_model: str,
    program_fragment: str,
    profile_version: str,
) -> str:
    payload = {
        "spec": spec,
        "semantics_model": semantics_model,
        "program_fragment": program_fragment,
        "profile_version": profile_version,
    }
    return "oblid:" + sha256_hex(canonical_json_bytes(payload))
