"""External-artifact slice generator (WI-2): upstream Boogie tests end to end.

The committed `corpora/external/upstream/*.bpl` files are verbatim copies of
the pinned boogie-org/boogie checkout (see PROVENANCE.json, fetched by
`tools/fetch_external.py`); `upstream_out/*.bpl` is a deterministic sample of
the out-of-subset remainder. This generator runs the full pipeline over them
and writes `corpora/external/expected.json`:

- per FILE: the import outcome (`imported` with obligation count, or the I7
  diagnostic kinds - out-of-subset files fail loud and are COUNTED);
- per OBLIGATION (in-subset files): the observed I4 status from the pinned z3
  (externally-authored programs have no designed verdicts - everything is
  observed, including refutations: upstream tests assert both);
- per obligation additionally: the Lean twin's rendered theorem + pinned-
  kernel attestation status (`attested`/`failed`/`timeout`, or
  `semantic-mismatch` when the term is outside the omega-provable subset) -
  the cross-backend downgrade rate is measured, never hidden.

Regeneration is offline (committed copies only), idempotent and deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.adapters.lean.backend import (  # noqa: E402
    PINNED_LEAN,
    TOOLCHAIN_ID,
    LeanBackend,
    LeanNotInstalled,
)
from uvil.adapters.lean.encode import (  # noqa: E402
    UnsupportedTermError,
    theorem_name,
    to_lean_theorem,
)
from uvil.adapters.smt.backends import SmtProcessError, verdict_status  # noqa: E402
from uvil.adapters.smt.encode import OpaqueTermError  # noqa: E402
from uvil.check.core import SmtBackend  # noqa: E402
from uvil.store import obligation_identity  # noqa: E402

EXTERNAL_DIR = REPO_ROOT / "corpora" / "external"
UPSTREAM_DIR = EXTERNAL_DIR / "upstream"
OUT_SAMPLE_DIR = EXTERNAL_DIR / "upstream_out"
LEAN_DIR = EXTERNAL_DIR / "lean"
EXPECTED_PATH = EXTERNAL_DIR / "expected.json"
PROVENANCE = json.loads((EXTERNAL_DIR / "PROVENANCE.json").read_text(encoding="utf-8"))

BUDGET_MS = 2000


def _identity(proc_name: str, fragment: str, obl) -> str:
    return obligation_identity(
        spec=obl.spec_ref,
        semantics_model=obl.semantics_model,
        program_fragment=fragment or proc_name,
        profile_version=obl.target_profile.rsplit("@", 1)[-1],
        sequent=obl.sequent,
    )


def generate() -> dict[str, object]:
    engine = SmtBackend("z3")
    expected: dict[str, dict[str, object]] = {}
    files: dict[str, dict[str, object]] = {}
    total_obligations = 0

    # --- in-subset upstream files: import -> z3 -> Lean twins ----------------
    lean_entries: dict[str, dict[str, object]] = {}
    for path in sorted(UPSTREAM_DIR.glob("*.bpl")):
        source = path.read_text(encoding="utf-8")
        result = import_module(source, path.name)
        if not result.ok or not result.obligations:
            # selection drift: upstream/ is the in-subset set by construction
            raise SystemExit(
                f"{path.name}: in-subset selection drifted ({[d.kind for d in result.diagnostics]})"
            )
        for proc in result.procedures.values():
            for obl in proc.obligations:
                total_obligations += 1
                obl_id = _identity(proc.name, proc.program.fragment or proc.name, obl)
                try:
                    status = verdict_status(engine.run(obl, budget=BUDGET_MS))
                except (SmtProcessError, OpaqueTermError, ValueError):
                    # ill-sorted scripts / unencodable terms: the obligation
                    # stays open (check() records the I7; open status pinned)
                    status = "open"
                expected[obl_id] = {
                    "file": path.name,
                    "proc": proc.name,
                    "expected": status,
                }
                try:
                    theorem = to_lean_theorem(obl)
                    lean_file = f"{theorem_name(obl)}.lean"
                    lean_entries[lean_file] = {
                        "obl_id": obl_id,
                        "theorem": theorem,
                        "lean_status": "pending",
                        "kernel_hash": None,
                    }
                except UnsupportedTermError:
                    lean_entries[f"(mismatch:{obl_id})"] = {
                        "obl_id": obl_id,
                        "theorem": None,
                        "lean_status": "semantic-mismatch",
                        "kernel_hash": None,
                    }
        files[path.name] = {
            "outcome": "imported",
            "obligations": sum(len(p.obligations) for p in result.procedures.values()),
            "diagnostics": 0,
        }

    # --- out-of-subset sample: the loud outcome is the pinned expectation ----
    out_outcomes: dict[str, dict[str, object]] = {}
    for path in sorted(OUT_SAMPLE_DIR.glob("*.bpl")):
        source = path.read_text(encoding="utf-8")
        result = import_module(source, path.name)
        kinds = sorted({d.kind for d in result.diagnostics})
        if result.ok and result.obligations:
            raise SystemExit(
                f"{path.name}: out-of-subset sample unexpectedly imports with "
                "obligations (selection drifted)"
            )
        if not kinds:
            raise SystemExit(f"{path.name}: neither obligations nor diagnostics - silent skip")
        out_outcomes[path.name] = {"diagnostic_kinds": kinds}

    # --- Lean kernel attestation over the rendered twins ---------------------
    attested = mismatch = 0
    try:
        backend = LeanBackend()
    except LeanNotInstalled:
        backend = None
        print("lean not installed: twins recorded with lean_status=pending", file=sys.stderr)
    lean_dir_files: dict[str, dict[str, object]] = {}
    for lean_file, entry in lean_entries.items():
        if entry["theorem"] is None:
            mismatch += 1
            lean_dir_files[lean_file] = entry
            continue
        if backend is None:
            lean_dir_files[lean_file] = entry
            continue
        verdict = backend.check_batch([str(entry["theorem"])])[0]
        entry["lean_status"] = verdict.status
        entry["kernel_hash"] = verdict.file_digest
        lean_dir_files[lean_file] = entry
        path = LEAN_DIR / lean_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((str(entry["theorem"]) + "\n").encode("utf-8"))
        if verdict.status == "attested":
            attested += 1

    # stale twin cleanup
    if LEAN_DIR.exists():
        for stale in LEAN_DIR.glob("*.lean"):
            if stale.name not in lean_dir_files:
                stale.unlink()

    total = len(lean_entries)
    open_count = sum(1 for e in expected.values() if e["expected"] == "open")
    meta = {
        "z3_pin": "5.1.0",
        "lean_pin": PINNED_LEAN,
        "toolchain": TOOLCHAIN_ID,
        "upstream_url": PROVENANCE["upstream_url"],
        "upstream_commit": PROVENANCE["upstream_commit"],
        "license": PROVENANCE["license"],
        "in_subset_files": len(list(UPSTREAM_DIR.glob("*.bpl"))),
        "obligations": total_obligations,
        "obligation_identities": len(expected),
        "open_obligations": open_count,
        "out_of_subset_sample_files": len(list(OUT_SAMPLE_DIR.glob("*.bpl"))),
        "full_upstream_scan": PROVENANCE["scan"],
        "lean_twins": total,
        "lean_attested": attested,
        "lean_semantic_mismatch": mismatch,
        "lean_downgrade_rate": round(mismatch / total, 4) if total else 0.0,
        "note": (
            "every expected status was OBSERVED with the pinned z3 at generation "
            "time (externally-authored programs carry no designed verdicts; "
            "refuted upstream asserts are recorded as-is). `obligations` counts "
            "every obligation; `obligation_identities` collapses the handful of "
            "cross-file identical procedures (same fragment/spec/sequent = the "
            "same verification claim, so the collapse is verdict-safe). The "
            "Lean-twin downgrade rate is measured over the same obligations; "
            "semantic-mismatch entries fail loud, never silent mistranslations. "
            "kernel_hash = sha256(theorem bytes + toolchain id); replay: uvil "
            "attest corpora/external/lean/<file>."
        ),
    }
    return {
        "meta": meta,
        "expected": expected,
        "files": {**files, **out_outcomes},
        "lean": lean_dir_files,
    }


def main() -> int:
    payload = generate()
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta = payload["meta"]
    print(
        f"wrote {EXPECTED_PATH}: {meta['obligations']} obligations from "
        f"{meta['in_subset_files']} upstream files ({meta['lean_attested']} "
        f"lean-attested, {meta['lean_semantic_mismatch']} semantic-mismatch)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
