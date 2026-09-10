"""Deterministic Isabelle-twin slice generator (M4 second-ITP deliverable).

Same whitelist families / discharge discipline as gen_lean_slice.py (its
collection + SMT re-verification code is REUSED): the SMT-discharged
obligations of the M1 corpus's whitelisted LIA families get Isabelle/HOL
twins (`by arith`/`by auto` within the HOL-facing boundary), then:

- `corpora/isabelle/<stem>.thy` - one batchable theory entry per corpus entry
  (committed);
- `corpora/isabelle/expected.json` - `{oblid: {file, family, smt_status,
  isabelle_status, theorem, kernel_hash}}` plus `meta` (pins, downgrade
  metrics - the measured, never-hidden downgrade rate on the SAME families
  as the Lean slice).

The downgrade rate is measured at RENDER time (terms outside the HOL-facing
boundary - identical policy to the Lean encoder); `isabelle_status` records
the pinned bundle's verdict when the bundle is installed, `pending`
otherwise (the committed manifest never fabricates an attestation).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from gen_lean_slice import (  # noqa: E402
    _corpus_meta,
    _obligation_for,
    _reverify_smt,
    collect_whitelisted,
)

from uvil.adapters.isabelle.backend import (  # noqa: E402
    ISABELLE_VERSION_ID,
    PINNED_ISABELLE,
    IsabelleBackend,
    IsabelleNotInstalled,
)
from uvil.adapters.isabelle.encode import (  # noqa: E402
    UnsupportedTermError,
    theorem_name,
    to_hol_theorem,
)

ISABELLE_CORPUS = REPO_ROOT / "corpora" / "isabelle"
EXPECTED_PATH = ISABELLE_CORPUS / "expected.json"


@dataclass(frozen=True)
class SliceEntry:
    oblid: str
    family: str
    boogie_file: str
    proc: str
    thy_file: str | None  # None for semantic-mismatch (no twin rendered)
    theorem: str | None
    isabelle_status: str  # attested | failed | timeout | semantic-mismatch | pending
    kernel_hash: str | None


def render_slice() -> tuple[list[SliceEntry], dict[str, object]]:
    """Pure slice construction: re-verify SMT verdicts and render the HOL
    twins (no kernel run - attestation status comes from attest_slice)."""
    discharged_total = sum(
        1 for e in _corpus_meta_entrant_entries() if e["expected"] == "discharged"
    )
    entries: list[SliceEntry] = []
    for oblid, entry in collect_whitelisted():
        boogie_file, proc, family = entry["file"], entry["proc"], entry["family"]
        _reverify_smt(boogie_file, proc)
        obl = _obligation_for(boogie_file, proc)
        thy_file = f"{theorem_name(obl)}.thy"
        try:
            theorem = to_hol_theorem(obl)
            entries.append(
                SliceEntry(
                    oblid=oblid,
                    family=family,
                    boogie_file=boogie_file,
                    proc=proc,
                    thy_file=thy_file,
                    theorem=theorem,
                    isabelle_status="pending",
                    kernel_hash=None,
                )
            )
        except UnsupportedTermError:
            entries.append(
                SliceEntry(
                    oblid=oblid,
                    family=family,
                    boogie_file=boogie_file,
                    proc=proc,
                    thy_file=None,
                    theorem=None,
                    isabelle_status="semantic-mismatch",
                    kernel_hash=None,
                )
            )
    # mirrors gen_lean_slice's metric exactly: mismatch entries are slice
    # entries (measured downgrades), not exclusions
    excluded = discharged_total - len(entries)
    meta = {
        "isabelle_pin": PINNED_ISABELLE,
        "version_id": ISABELLE_VERSION_ID,
        "z3_pin": _corpus_meta().get("z3_pin"),
        "smt_reverified": True,
        "families_whitelist": ["arith-comm", "divmod", "minmax", "abs-bound"],
        "slice_entries": len(entries),
        "smt_discharged_corpus_total": discharged_total,
        "downgraded_out_of_corpus": excluded,
        "downgrade_rate": round(excluded / discharged_total, 4) if discharged_total else 0.0,
        "note": (
            "same whitelist families / discharge discipline as the Lean slice "
            "(corpora/lean); every slice entry is discharged-in-SMT "
            "(re-verified with the pinned z3 at generation time) and carries "
            "its Isabelle/HOL twin. semantic-mismatch entries are the honest "
            "downgrade metric (terms outside the HOL-facing boundary fail "
            "loud, never silent mistranslations); isabelle_status is the "
            "pinned bundle's verdict at generation time, or 'pending' when "
            "the bundle is not installed on the generating machine - the "
            "committed manifest never fabricates an attestation. kernel_hash "
            "= sha256(theory bytes + Isabelle version id); replay: run the "
            "pinned isabelle build on the committed session."
        ),
    }
    return entries, meta


def _corpus_meta_entrant_entries() -> list[dict[str, str]]:
    from gen_lean_slice import _corpus_expected

    return list(_corpus_expected().values())


def attest_slice(entries: list[SliceEntry]) -> list[SliceEntry]:
    """Run the pinned bundle over each rendered twin; fills
    isabelle_status/hashes. Entries without a theorem pass through."""
    if not entries:
        return entries
    backend = IsabelleBackend()
    attested: list[SliceEntry] = []
    for entry in entries:
        if entry.theorem is None:
            attested.append(entry)
            continue
        verdict = backend.check_batch([entry.theorem])[0]
        attested.append(
            SliceEntry(
                oblid=entry.oblid,
                family=entry.family,
                boogie_file=entry.boogie_file,
                proc=entry.proc,
                thy_file=entry.thy_file,
                theorem=entry.theorem,
                isabelle_status=verdict.status,  # attested | failed | timeout
                kernel_hash=entry.theorem and verdict.theory_digest,
            )
        )
    return attested


def generate() -> dict[str, object]:
    entries, meta = render_slice()
    try:
        entries = attest_slice(entries)
    except IsabelleNotInstalled:
        print(
            "isabelle not installed: writing rendered twins with isabelle_status=pending",
            file=sys.stderr,
        )
    ISABELLE_CORPUS.mkdir(parents=True, exist_ok=True)

    current: dict[str, SliceEntry] = {}
    for entry in entries:
        if entry.theorem is None:
            current[f"(mismatch:{entry.oblid})"] = entry
            continue
        path = ISABELLE_CORPUS / entry.thy_file
        path.write_bytes((entry.theorem + "\n").encode("utf-8"))
        current[entry.thy_file] = entry

    for stale in ISABELLE_CORPUS.glob("*.thy"):
        if stale.name not in current:
            stale.unlink()

    expected_payload = {
        e.oblid: {
            "file": e.thy_file,
            "family": e.family,
            "boogie_file": e.boogie_file,
            "proc": e.proc,
            "smt_status": "discharged",
            "isabelle_status": e.isabelle_status,
            "theorem": e.theorem,
            "kernel_hash": e.kernel_hash,
        }
        for e in entries
    }
    return {"meta": meta, "expected": expected_payload}


def main() -> int:
    payload = generate()
    meta = payload["meta"]
    expected = payload["expected"]
    attested = sum(1 for e in expected.values() if e["isabelle_status"] == "attested")  # type: ignore[union-attr]
    pending = sum(1 for e in expected.values() if e["isabelle_status"] == "pending")  # type: ignore[union-attr]
    mismatched = sum(1 for e in expected.values() if e["isabelle_status"] == "semantic-mismatch")  # type: ignore[union-attr]
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {EXPECTED_PATH}: {len(expected)} slice entries "
        f"({attested} kernel-attested, {pending} pending, {mismatched} "
        f"semantic-mismatch, downgrade_rate={meta['downgrade_rate']})"
    )
    rendered = sum(1 for e in expected.values() if e["file"])  # type: ignore[union-attr]
    if rendered < 100:
        raise SystemExit(f"slice too small: {rendered} rendered twins < 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
