"""Incremental check: cache-partitioned dispatch with Merkle-diff evidence.

`check_incremental` is the M5 incremental protocol around `check/core.py`:

- Each obligation gets an identity via `store.identity.obligation_identity`
  over `(spec_ref, semantics_model, program_ref, profile_version)`: the spec
  and program artifact refs are content hashes of the I2/I3 artifacts, so the
  M0 identity tuple is fully determined by the obligation (the program
  fragment travels inside its artifact hash). A no-op change (context reorder
  or formatting that leaves the I2/I3 artifacts untouched) keeps the identity
  and hits the cache; any real spec/code/library churn changes some component
  and misses.
- Hits are reused with no solver call (their verdicts enter the I8 run with
  `time_ms=None`; `Run.config["cached"]` lists the reused refs). Misses go
  through plain `check()`; only freshly `discharged` misses update the cache.
- Evidence: a Merkle diff (`store/merkle.py`, sorted-leaf canonical tree) of
  the identity set, old (known cache identities, optionally filtered by
  `incremental_since=<seq>`) vs new (the submitted set): roots plus
  added/removed/unchanged identity lists. The old set is captured before any
  cache update, so the diff reflects the state the run started from.

Fail-loud invariants: a cached verdict is reused only on an exact key match
(identity + backend + tool pin + protocol version); `unknown`/`timeout` are
never cached as success; the reused obligations are recorded exactly like
fresh ones (`record()` is unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..artifacts import Run, Verdict, artifact_id
from ..artifacts.obligation import Obligation
from ..artifacts.run import ToolDescriptor
from ..check.core import CheckResult, SmtBackend, check, record
from ..ledger import Ledger
from ..store import ContentStore, merkle_root
from ..store.identity import obligation_identity
from .cache import VerdictCache

CACHE_FILENAME = "verdict-cache.json"


@dataclass
class IncrementalResult:
    """The incremental outcome around a normal `CheckResult` (not an artifact)."""

    result: CheckResult
    reused: list[str] = field(default_factory=list)  # obligation artifact ids
    recomputed: list[str] = field(default_factory=list)  # obligation artifact ids
    merkle: dict[str, object] = field(default_factory=dict)


def obligation_cache_identity(obl: Obligation) -> str:
    """The cache identity of an obligation artifact (M0 identity tuple)."""
    return obligation_identity(
        spec=obl.spec_ref,
        semantics_model=obl.semantics_model,
        program_fragment=obl.program_ref,
        profile_version=obl.target_profile.rsplit("@", 1)[-1],
    )


def _merkle_diff(old: set[str], new: set[str]) -> dict[str, object]:
    return {
        "old_root": merkle_root(sorted(old)),
        "new_root": merkle_root(sorted(new)),
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "unchanged": sorted(old & new),
    }


def check_incremental(
    obligations: list[Obligation],
    store: ContentStore,
    ledger: Ledger,
    backend: str = "z3",
    timeout_ms: int | None = None,
    discipline: str = "none",
    incremental_since: int | None = None,
) -> IncrementalResult:
    """Check obligations with verdict reuse: hits skip the solver, misses solve."""
    if discipline not in ("none", "roundtrip"):
        raise ValueError(f"unknown discipline: {discipline!r} (expected 'none' or 'roundtrip')")
    if not obligations:
        raise ValueError("check_incremental() requires at least one obligation")
    engine = SmtBackend(backend)
    cache = VerdictCache(store.root / CACHE_FILENAME)

    identities = {artifact_id(obl): obligation_cache_identity(obl) for obl in obligations}
    by_ref = {artifact_id(obl): obl for obl in obligations}
    old_known = cache.known_identities(incremental_since)  # pre-run state, pre-update

    reused_refs: list[str] = []
    miss_refs: list[str] = []
    for ref, ident in identities.items():
        entry = cache.get(ident, backend, engine.version)
        if entry is not None and (
            incremental_since is None or entry.ledger_seq <= incremental_since
        ):
            reused_refs.append(ref)
        else:
            miss_refs.append(ref)

    misses = [by_ref[ref] for ref in miss_refs]
    if misses:
        fresh = check(misses, backend=backend, timeout_ms=timeout_ms, discipline=discipline)
        fresh_run = fresh.run
        assert fresh_run is not None
        fresh_config = fresh_run.config
    else:
        fresh = CheckResult()
        fresh_run = None
        fresh_config = {"backend": backend, "timeout_ms": timeout_ms, "discipline": discipline}

    # Merge: submission order; hits are marked cached (no solver call, no timing).
    verdicts: list[Verdict] = []
    merged_status: dict[str, str] = {}
    for ref in identities:
        if ref in reused_refs:
            verdicts.append(Verdict(obligation_ref=ref, status="discharged", time_ms=None))
            merged_status[ref] = "discharged"
    if fresh_run is not None:
        for verdict in fresh_run.verdicts:
            verdicts.append(verdict)
            merged_status[verdict.obligation_ref] = verdict.status
    run = Run(
        tool=ToolDescriptor(name=backend, version=engine.version, flags=[]),
        config={**fresh_config, "incremental": True, "cached": reused_refs},
        verdicts=verdicts,
    )
    result = CheckResult(
        obligations=[
            by_ref[ref].model_copy(update={"status": merged_status[ref]}) for ref in identities
        ],
        counterexamples=fresh.counterexamples,
        diagnostics=fresh.diagnostics,
        translations=fresh.translations,
        run=run,
    )

    # Record exactly as a plain check would (reused obligations land in the
    # I8 run + CAS + the G1 entry), then cache newly discharged misses.
    record(result, store, ledger)
    seq = ledger.entries()[-1].seq
    run_ref = artifact_id(run)
    for ref in miss_refs:
        if merged_status[ref] == "discharged":
            cache.put(
                identities[ref],
                backend,
                engine.version,
                obligation_ref=ref,
                run_ref=run_ref,
                ledger_seq=seq,
                status="discharged",
            )

    return IncrementalResult(
        result=result,
        reused=reused_refs,
        recomputed=miss_refs,
        merkle=_merkle_diff(old_known, set(identities.values())),
    )
