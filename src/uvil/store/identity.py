"""Obligation identity - the M5 incremental-protocol cache key.

`identity = sha256(canonical(spec, semantics_model, program_fragment,
profile_version, canonical-sequent))` (draft §5.6 as amended by ADR 0008).

The sequent component (ADR 0008): one procedure yields multiple obligations
under the WP VCG (initiation / preservation / per-assert), all sharing the
M0 tuple, so the tuple alone cannot key the verdict cache soundly. The
canonical sequent - the goal plus the context with its ORDER normalized away -
distinguishes them. Order normalization is what keeps the churn benchmark's
no-op-reorder control a cache hit: reversing the sequent context (pure
formatting churn) leaves the canonical form untouched. Getting
canonicalization right first matters: changing it later invalidates all
identity-keyed corpora.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..artifacts.base import canonical_json_bytes, sha256_hex
from ..artifacts.obligation import Sequent
from ..artifacts.terms import Term


def _canonical_sequent(context: Sequence[Term], goal: Term) -> dict[str, object]:
    return {
        # context order is normalized away (no-op formatting churn stays a hit)
        "context": sorted(
            canonical_json_bytes(t.model_dump(mode="json")).decode("utf-8") for t in context
        ),
        "goal": canonical_json_bytes(goal.model_dump(mode="json")).decode("utf-8"),
    }


def obligation_identity(
    spec: str,
    semantics_model: str,
    program_fragment: str,
    profile_version: str,
    sequent: Sequent,
) -> str:
    payload = {
        "spec": spec,
        "semantics_model": semantics_model,
        "program_fragment": program_fragment,
        "profile_version": profile_version,
        "sequent": _canonical_sequent(sequent.context, sequent.goal),
    }
    return "oblid:" + sha256_hex(canonical_json_bytes(payload))
