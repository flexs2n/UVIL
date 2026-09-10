"""Deterministic Lean-twin slice generator (M3 exit criterion).

Takes the SMT-discharged obligations of the M1 corpus's whitelisted LIA
families and renders their Lean twins (`omega` scaffolding), then attests
each twin with the pinned kernel and writes:

- `corpora/lean/<stem>.lean`  - one standalone theorem per corpus entry
- `corpora/lean/expected.json` -
    `{oblid: {file, family, smt_status, lean_status, theorem, kernel_hash}}`
    plus `meta` (pins, downgrade metrics).

Discipline (mirrors gen_corpus.py):
- whitelist fixed by the discovery tests (tests/test_lean_discovery.py):
  `omega` handles linear Int arithmetic, `ite` on Int (minmax/abs-bound in),
  and div/mod ONLY with positive constant divisors (constant-pin propagation
  of `requires b == K`; curated `requires b > 0` entries stay unsliced and
  surface as semantic-mismatch - measured, never hidden);
- SMT-discharged is re-verified with the pinned z3 before an entry joins the
  slice (a disagreement is a hard error);
- unsupported terms (nonlinear `*` e.g. `neg_mul`'s `(-a) * b`, variable
  divisors, ...) fail loud as I7-shaped `semantic-mismatch` entries - the
  downgrade rate is stated in `meta`;
- regeneration is idempotent and deterministic: stale files are removed,
  identical inputs reproduce byte-identical files.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
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
from uvil.adapters.lean.encode import (
    UnsupportedTermError,
    theorem_name,
    to_lean_theorem,
)
from uvil.adapters.smt.backends import verdict_status  # noqa: E402
from uvil.check.core import SmtBackend  # noqa: E402

BOOGIE_CORPUS = REPO_ROOT / "corpora" / "boogie"
LEAN_CORPUS = REPO_ROOT / "corpora" / "lean"
EXPECTED_PATH = LEAN_CORPUS / "expected.json"

# Fixed by the discovery tests (ite-on-Int supported; div/mod needs positive
# constant divisors via constant-pin propagation). Everything else -
# distrib/sq-sum (nonlinear mul), arr-*/seq-* (no encoding), loop-inv,
# refut-*/nonlinear-unknown/timeout (not SMT-discharged) - stays out and is
# counted in the downgrade metrics.
WHITELIST_FAMILIES = ("arith-comm", "divmod", "minmax", "abs-bound")


@dataclass(frozen=True)
class SliceEntry:
    oblid: str
    family: str
    boogie_file: str
    proc: str
    lean_file: str | None  # None for semantic-mismatch (no twin rendered)
    theorem: str | None
    lean_status: str  # attested | unproved | timeout | semantic-mismatch
    kernel_hash: str | None


def _corpus_expected() -> dict[str, dict[str, str]]:
    data = json.loads((BOOGIE_CORPUS / "expected.json").read_text(encoding="utf-8"))
    return data["expected"]


def _corpus_meta() -> dict[str, object]:
    data = json.loads((BOOGIE_CORPUS / "expected.json").read_text(encoding="utf-8"))
    return data["meta"]


def collect_whitelisted() -> list[tuple[str, dict[str, str]]]:
    """The SMT-discharged obligations of whitelisted families."""
    expected = _corpus_expected()
    out = []
    for oblid, entry in sorted(expected.items()):
        if entry["family"] not in WHITELIST_FAMILIES:
            continue
        if entry["expected"] != "discharged":
            continue
        out.append((oblid, entry))
    return out


def _reverify_smt(boogie_file: str, proc: str) -> None:
    """Fail loud unless the pinned z3 still discharges the obligation."""
    result = import_module((BOOGIE_CORPUS / boogie_file).read_text(encoding="utf-8"), boogie_file)
    assert result.ok, [d.native_message for d in result.diagnostics]
    (obl,) = [o for p in result.procedures.values() for o in p.obligations if p.name == proc]
    engine = SmtBackend("z3")
    status = verdict_status(engine.run(obl, budget=2000))
    if status != "discharged":
        raise SystemExit(f"{boogie_file}/{proc}: corpus says discharged but z3 returned {status}")


def _obligation_for(boogie_file: str, proc: str):
    result = import_module((BOOGIE_CORPUS / boogie_file).read_text(encoding="utf-8"), boogie_file)
    assert result.ok, [d.native_message for d in result.diagnostics]
    matches = [o for p in result.procedures.values() for o in p.obligations if p.name == proc]
    assert len(matches) == 1, f"{boogie_file}/{proc}: expected exactly one obligation"
    return matches[0]


def render_slice() -> tuple[list[SliceEntry], dict[str, object]]:
    """Pure slice construction: re-verify SMT verdicts and render the Lean
    twins (no kernel run - attestation status comes from attest_slice)."""
    expected = _corpus_expected()
    discharged_total = sum(1 for e in expected.values() if e["expected"] == "discharged")
    entries: list[SliceEntry] = []
    for oblid, entry in collect_whitelisted():
        boogie_file, proc, family = entry["file"], entry["proc"], entry["family"]
        _reverify_smt(boogie_file, proc)
        obl = _obligation_for(boogie_file, proc)
        # one .lean per obligation, named after its stable theorem name
        # (multi-procedure files like negatives.bpl never collide)
        lean_file = f"{theorem_name(obl)}.lean"
        try:
            theorem = to_lean_theorem(obl)
            entries.append(
                SliceEntry(
                    oblid=oblid,
                    family=family,
                    boogie_file=boogie_file,
                    proc=proc,
                    lean_file=lean_file,
                    theorem=theorem,
                    lean_status="pending",
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
                    lean_file=None,
                    theorem=None,
                    lean_status="semantic-mismatch",
                    kernel_hash=None,
                )
            )
    excluded = discharged_total - len(entries)
    meta = {
        "lean_pin": PINNED_LEAN,
        "toolchain": TOOLCHAIN_ID,
        "z3_pin": _corpus_meta().get("z3_pin"),
        "smt_reverified": True,
        "families_whitelist": list(WHITELIST_FAMILIES),
        "slice_entries": len(entries),
        "smt_discharged_corpus_total": discharged_total,
        "downgraded_out_of_corpus": excluded,
        "downgrade_rate": round(excluded / discharged_total, 4) if discharged_total else 0.0,
        "note": (
            "every slice entry is discharged-in-SMT (re-verified with the pinned "
            "z3 at generation time) and carries its Lean twin; lean_status records "
            "the pinned kernel's verdict at generation time. semantic-mismatch "
            "entries are the honest downgrade metric (unsupported terms fail loud, "
            "never silent mistranslations). kernel_hash = sha256(theorem bytes + "
            "toolchain id); replay: run the pinned lean on the .lean file."
        ),
    }
    return entries, meta


def attest_slice(entries: list[SliceEntry]) -> list[SliceEntry]:
    """Run the pinned kernel on each rendered twin; fills lean_status/hashes.
    Entries already marked semantic-mismatch pass through untouched."""
    if not entries:
        return entries
    backend = LeanBackend()
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
                lean_file=entry.lean_file,
                theorem=entry.theorem,
                lean_status=verdict.status,  # attested | failed | timeout
                kernel_hash=entry.theorem and verdict.file_digest,
            )
        )
    return attested


def generate() -> dict[str, object]:
    entries, meta = render_slice()
    try:
        entries = attest_slice(entries)
    except LeanNotInstalled:
        print(
            "lean not installed: writing rendered twins with lean_status=pending", file=sys.stderr
        )
    LEAN_CORPUS.mkdir(parents=True, exist_ok=True)

    current: dict[str, SliceEntry] = {}
    for entry in entries:
        if entry.theorem is None:
            current[f"(mismatch:{entry.oblid})"] = entry
            continue
        path = LEAN_CORPUS / entry.lean_file
        # byte-exact write (the kernel hash commits to these exact bytes; no
        # newline translation - write_text would produce CRLF on Windows)
        path.write_bytes((entry.theorem + "\n").encode("utf-8"))
        current[entry.lean_file] = entry

    # stale cleanup: files from earlier runs that are no longer in the slice
    for stale in LEAN_CORPUS.glob("*.lean"):
        if stale.name not in current:
            stale.unlink()

    expected_payload = {
        e.oblid: {
            "file": e.lean_file,
            "family": e.family,
            "boogie_file": e.boogie_file,
            "proc": e.proc,
            "smt_status": "discharged",
            "lean_status": e.lean_status,
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
    attested = sum(1 for e in expected.values() if e["lean_status"] == "attested")
    mismatched = sum(1 for e in expected.values() if e["lean_status"] == "semantic-mismatch")
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {EXPECTED_PATH}: {len(expected)} slice entries "
        f"({attested} kernel-attested, {mismatched} semantic-mismatch, "
        f"downgrade_rate={meta['downgrade_rate']})"
    )
    if attested < 100:
        raise SystemExit(f"slice too small: {attested} attested < 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
