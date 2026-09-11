"""Deterministic VeriContest slice generator (M6, ADR 0009).

The VeriContest harvest (the closed ADR 0007 deferral): a deterministic
sample of upstream tasks (committed verbatim by `tools/fetch_vericontest.py`)
plus a `generated/` set of UVIL-authored in-subset harnesses (the
strata-corpus precedent - safe + refutable), and:

- `corpora/vericontest/generated/*.rs` - one in-subset procedure per file
  (committed);
- `corpora/vericontest/expected.json` - per task: the NATIVE Verus verdict
  (the ground-truth arm: pinned `verus <file>` exit code + verbatim results
  line at generation time), the IMPORT outcome (`import_verus`: procedures
  or the I7 diagnostic kind), and for in-subset files the UVIL z3
  re-dispatch verdict per obligation - the backend-invariance comparison.

Three measured facts drive the paper metric (all recorded, none hidden):
1. the upstream downgrade rate (out-of-subset tasks / sampled tasks) - ALL
   1007 upstream `verified.rs` files are out of the scalar-contract subset
   (Seq/quantifier/loop/struct fragments; scanned at fetch time), so this
   is 1.000 on any sample: competitive-programming proofs ARE
   loop/sequence-shaped, and the honest slice boundary reflects it;
2. the native ground-truth arm (pinned Verus on every sampled task);
3. the in-subset agreement metric (native Verus verdict vs UVIL z3 verdict
   per generated harness): carried by the generated harnesses because the
   upstream sample has an empty in-subset set - recorded as n/a there, and
   every disagreement (none at generation time) would be a finding.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from uvil.adapters.smt.backends import verdict_status  # noqa: E402
from uvil.adapters.verus.importer import (  # noqa: E402
    PINNED_VERUS_COMMIT,
    PINNED_VERUS_TAG,
    PINNED_VERUS_TOOLCHAIN,
    PINNED_VERUS_Z3,
    find_verus,
    import_verus,
    verus_verify,
)
from uvil.check.core import SmtBackend  # noqa: E402

VERICONTEST_DIR = REPO_ROOT / "corpora" / "vericontest"
UPSTREAM_DIR = VERICONTEST_DIR / "upstream"
GENERATED_DIR = VERICONTEST_DIR / "generated"
EXPECTED_PATH = VERICONTEST_DIR / "expected.json"

HARNESS_TEMPLATE = """use vstd::prelude::*;

fn main() {}

verus! {

fn @NAME@(x: i32@EXTRA_PARAMS@)
    requires @REQUIRES@,
    ensures @ENSURES@,
{
@BODY@}

}
"""

# One in-subset procedure per file (a file-level native verdict therefore maps
# 1:1 to the procedure - the comparison unit). The native verdicts below were
# confirmed live against the pinned release before committing.
HARNESSES: dict[str, dict[str, str]] = {
    "gen_add_comm": {
        "params": ", y: i32",
        "requires": "x >= 0, y >= 0",
        "ensures": "x + y == y + x",
        "body": "",
        "native": "verified",
    },
    "gen_add_id": {
        "params": "",
        "requires": "x >= 0",
        "ensures": "x + 0 == x",
        "body": "",
        "native": "verified",
    },
    "gen_bound_chain": {
        "params": ", y: i32",
        "requires": "x >= 0, y >= x",
        "ensures": "y >= x",
        "body": "",
        "native": "verified",
    },
    "gen_distrib": {
        "params": "",
        "requires": "x >= 0, x <= 1000",
        "ensures": "x * 2 == x + x",
        "body": "",
        "native": "verified",
    },
    "gen_refute_bound": {
        "params": ", y: i32",
        "requires": "x >= 0",
        "ensures": "x - y == 10",
        "body": "",
        "native": "failed",
    },
    "gen_refute_double": {
        "params": "",
        "requires": "x == 5",
        "ensures": "x * 2 == 12",
        "body": "",
        "native": "failed",
    },
}


@dataclass(frozen=True)
class SliceEntry:
    task: str
    family: str  # upstream | generated
    import_kind: str  # procedures | diagnostic
    import_detail: str  # obligation count or the I7 diagnostic kind
    native_status: str  # verified | failed | unsupported-locally | pending
    native_exit_code: int | None
    native_results_line: str | None
    z3_status: str | None  # in-subset only: discharged | refuted | open | timeout
    agreement: str | None  # agree | disagree | None (out-of-subset / pending)


def _native_status_of(exit_code: int, raw: str) -> str:
    if exit_code == 0:
        return "verified"
    if "postcondition not satisfied" in raw or "verification results::" in raw:
        return "failed"
    return "unsupported-locally"


def _results_line(raw: str) -> str | None:
    for line in raw.splitlines():
        if line.strip().startswith("verification results::"):
            return line.strip()
    return None


def _render_harness(name: str, spec: dict[str, str]) -> str:
    body = spec["body"]
    text = HARNESS_TEMPLATE
    for placeholder, value in (
        ("@NAME@", name),
        ("@EXTRA_PARAMS@", spec["params"]),
        ("@REQUIRES@", spec["requires"]),
        ("@ENSURES@", spec["ensures"]),
        ("@BODY@", body),
    ):
        text = text.replace(placeholder, value)
    return text


def generate() -> dict[str, object]:
    verus = find_verus()
    engine = SmtBackend("z3")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in HARNESSES.items():
        (GENERATED_DIR / f"{name}.rs").write_text(
            _render_harness(name, spec), encoding="utf-8", newline="\n"
        )

    entries: list[SliceEntry] = []

    # --- the upstream sample: import scan + native ground truth -----------
    upstream_tasks = sorted(d for d in UPSTREAM_DIR.iterdir() if d.is_dir())
    if not upstream_tasks:
        raise SystemExit("no upstream tasks - run tools/fetch_vericontest.py first")
    for task in upstream_tasks:
        source = (task / "verified.rs").read_text(encoding="utf-8", errors="replace")
        result = import_verus(source, f"{task.name}.rs")
        if result.procedures and not result.diagnostics:
            import_kind, import_detail = (
                "procedures",
                str(sum(len(p.obligations) for p in result.procedures.values())),
            )
        elif result.diagnostics:
            import_kind, import_detail = "diagnostic", result.diagnostics[0].kind
        else:
            import_kind, import_detail = "empty", "no procedures, no diagnostics"

        native_status, native_exit, native_line = "pending", None, None
        if verus is not None:
            run = verus_verify(verus, task / "verified.rs")
            native_status = _native_status_of(run.exit_code, run.raw_output)
            native_exit, native_line = run.exit_code, _results_line(run.raw_output)
        entries.append(
            SliceEntry(
                task=f"upstream/{task.name}",
                family="upstream",
                import_kind=import_kind,
                import_detail=import_detail,
                native_status=native_status,
                native_exit_code=native_exit,
                native_results_line=native_line,
                z3_status=None,
                agreement=None,
            )
        )

    # --- the generated harnesses: the in-subset agreement metric ----------
    for name, spec in HARNESSES.items():
        path = GENERATED_DIR / f"{name}.rs"
        source = path.read_text(encoding="utf-8")
        result = import_verus(source, path.name)
        if not (result.procedures and not result.diagnostics):
            raise SystemExit(
                f"generated harness {name} must import cleanly: "
                f"{[d.native_message for d in result.diagnostics]}"
            )
        obligations = result.obligations
        z3_statuses = [
            verdict_status(engine.run(o, budget=o.cost_budget.solver_ms)) for o in obligations
        ]
        expected_native = spec["native"]
        expected_z3 = "discharged" if expected_native == "verified" else "refuted"
        observed_z3 = z3_statuses[0] if len(set(z3_statuses)) == 1 else "mixed"
        native_status, native_exit, native_line = "pending", None, None
        if verus is not None:
            run = verus_verify(verus, path)
            native_status = _native_status_of(run.exit_code, run.raw_output)
            native_exit, native_line = run.exit_code, _results_line(run.raw_output)
        if native_status == "pending" or observed_z3 == "mixed":
            agreement = None
        elif native_status == expected_native and observed_z3 == expected_z3:
            agreement = "agree"
        else:
            agreement = "disagree"
        entries.append(
            SliceEntry(
                task=f"generated/{name}",
                family="generated",
                import_kind="procedures",
                import_detail=str(len(obligations)),
                native_status=native_status,
                native_exit_code=native_exit,
                native_results_line=native_line,
                z3_status=observed_z3,
                agreement=agreement,
            )
        )

    upstream_entries = [e for e in entries if e.family == "upstream"]
    downgraded = sum(
        1 for e in upstream_entries if e.import_kind == "diagnostic" or e.import_kind == "empty"
    )
    in_subset = [e for e in entries if e.family == "generated"]
    agreed = sum(1 for e in in_subset if e.agreement == "agree")
    disagreed = [e.task for e in in_subset if e.agreement == "disagree"]
    native_run = sum(1 for e in entries if e.native_status != "pending")
    meta = {
        "verus_tag": PINNED_VERUS_TAG,
        "verus_commit": PINNED_VERUS_COMMIT,
        "verus_toolchain": PINNED_VERUS_TOOLCHAIN,
        "verus_z3_pin": PINNED_VERUS_Z3,
        "z3_pin": "5.1.0",
        "sample_size": len(upstream_entries),
        "native_runs_completed": native_run,
        "upstream_downgraded": downgraded,
        "upstream_downgrade_rate": round(downgraded / len(upstream_entries), 4),
        "in_subset_entries": len(in_subset),
        "in_subset_agreement": f"{agreed}/{len(in_subset)}",
        "disagreements": disagreed,
        "note": (
            "the ground-truth arm is the pinned Verus release on the committed "
            "bytes (run records with exit codes + verbatim results lines - "
            "native verdicts are run records, never I5 proofs); the import arm "
            "re-dispatches the in-subset sequents through UVIL's own pinned z3 "
            "(unbounded-Int harness abstraction - the native verdict never "
            "upgrades an obligation). ALL sampled upstream tasks are out of "
            "the scalar-contract subset, so the downgrade rate is the honest "
            "headline (1.000 on this sample) and the in-subset agreement "
            "metric is carried by the generated harnesses; a disagreement "
            "would be a finding recorded here, never papered over."
        ),
    }
    payload = {
        "meta": meta,
        "expected": {
            e.task: {
                "family": e.family,
                "import_kind": e.import_kind,
                "import_detail": e.import_detail,
                "native_status": e.native_status,
                "native_exit_code": e.native_exit_code,
                "native_results_line": e.native_results_line,
                "z3_status": e.z3_status,
                "agreement": e.agreement,
            }
            for e in entries
        },
    }
    return payload


def main() -> int:
    payload = generate()
    meta = payload["meta"]
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {EXPECTED_PATH}: {len(payload['expected'])} entries "
        f"(downgrade_rate={meta['upstream_downgrade_rate']}, "
        f"agreement={meta['in_subset_agreement']}, "
        f"native_runs={meta['native_runs_completed']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
