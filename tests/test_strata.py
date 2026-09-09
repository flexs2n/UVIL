"""Strata import adapter tests: real pinned artifacts, vendor-TCB discipline.

- (no strata needed) import of the verbatim upstream fixtures of the pinned
  checkout + the generated in-subset harnesses; golden snapshots; manifest
  coherence + regeneration determinism;
- (z3, always available) the re-dispatch discipline: imported obligations are
  ordinary I4s - UVIL's own z3 discharges/refutes them; the vendor pipeline is
  never trusted;
- (vendor stub) the UVIL_STRATA plumbing: a stub binary stands in for the
  pinned Strata-CLI, pinning that vendor verdicts are recorded VERBATIM as
  opaque I5 payloads (format="strata-verifier-result", independent=False) and
  never become guarantees (no ledger entry, no status upgrade).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from uvil.adapters.strata.importer import (
    PINNED_STRATA_COMMIT,
    STRATA_ENV_VAR,
    VENDOR_PAYLOAD_FORMAT,
    import_strata,
)
from uvil.check.core import check as run_check
from uvil.check.core import record as record_check
from uvil.ledger import Ledger
from uvil.store import ContentStore

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATA_CORPUS = REPO_ROOT / "corpora" / "strata"


def _manifest() -> dict:
    return json.loads((STRATA_CORPUS / "expected.json").read_text(encoding="utf-8"))


def _import_entry(rel: str):
    source = (STRATA_CORPUS / rel).read_text(encoding="utf-8")
    return import_strata(source, filename=rel)


# --- upstream fixtures of the pinned checkout (no strata needed) --------------------


def test_manifest_pins_provenance() -> None:
    meta = _manifest()["meta"]
    provenance = meta["provenance"]
    assert provenance["commit"] == PINNED_STRATA_COMMIT
    assert provenance["repo"] == "https://github.com/strata-org/Strata"
    assert provenance["toolchain"] == "leanprover/lean4:v4.29.1"
    assert "NOT UVIL's TCB" in provenance["note"]


def test_upstream_import_shapes_match_manifest() -> None:
    for rel, entry in _manifest()["expected"].items():
        result = _import_entry(rel)
        assert sorted(result.procedures) == sorted(entry["procedures"]), rel
        assert len(result.obligations) == entry["obligations"], rel
        kinds = sorted(d.kind for d in result.diagnostics)
        assert kinds == sorted(entry["diagnostics"]), rel


def test_upstream_simple_proc_spec_is_preserved() -> None:
    result = _import_entry("upstream/SimpleProc.core.st")
    assert result.ok
    (proc,) = result.procedures.values()
    assert proc.program.language == "strata-core"
    assert proc.program.semantics_model == "model:strata-core.v1"
    assert len(proc.spec.contracts.ensures) == 2
    assert proc.obligations == []  # no asserts in the body (honest: no WP)


def test_out_of_subset_fragments_travel_verbatim() -> None:
    # bv types and Map types have no shared-theory semantics: the verbatim
    # source lines are preserved (fail loud, R3)
    result = _import_entry("upstream/SafeBvOps.core.st")
    (diag,) = result.diagnostics
    assert diag.kind == "semantic-mismatch"
    assert "type 'bv'" in diag.native_message
    assert "procedure safe_bv_ops(x: bv W32" in diag.native_message

    result = _import_entry("upstream/TypeError.core.st")
    (diag,) = result.diagnostics
    assert diag.kind == "semantic-mismatch"
    assert "type 'Map'" in diag.native_message
    assert "procedure foo(out y : Map int int)" in diag.native_message


def test_cfg_and_while_fail_loud_with_verbatim_line() -> None:
    result = _import_entry("upstream/CFGSimple.core.st")
    (diag,) = result.diagnostics
    assert diag.kind == "parse"
    assert "CFG" in diag.native_message

    result = _import_entry("upstream/LoopSimple.core.st")
    (diag,) = result.diagnostics
    assert diag.kind == "parse"
    assert "while" in diag.native_message


def test_csimp_dialect_is_rejected() -> None:
    result = _import_entry("upstream/LoopSimple.csimp.st")
    (diag,) = result.diagnostics
    assert diag.kind == "parse"
    assert "dialect" in diag.native_message


# --- generated in-subset harnesses: the re-dispatch discipline -----------------------


def test_generated_imports_are_in_subset() -> None:
    for rel, entry in _manifest()["expected"].items():
        if not rel.startswith("generated/"):
            continue
        result = _import_entry(rel)
        assert result.ok, rel
        assert len(result.obligations) == entry["obligations"], rel


def test_import_snapshot(snapshot: SnapshotAssertion) -> None:
    result = _import_entry("generated/gen_assign_forward.st")
    (proc,) = result.procedures.values()
    (obl,) = proc.obligations
    payload = {
        "sequent": {
            "context": [c.model_dump(mode="json") for c in obl.sequent.context],
            "goal": obl.sequent.goal.model_dump(mode="json"),
            "var_sorts": obl.sequent.var_sorts,
        },
        "theories": obl.theories,
        "origin_backend": obl.origin_backend,
        "target_profile": obl.target_profile,
        "semantics_model": obl.semantics_model,
        "program_notes": proc.program.notes,
    }
    assert payload == snapshot


def test_regeneration_is_deterministic() -> None:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import gen_strata_corpus

    payload_a = gen_strata_corpus.generate()
    payload_b = gen_strata_corpus.generate()
    assert payload_a == payload_b
    assert payload_a == _manifest()


# --- UVIL's own backends decide (z3 always available) ---------------------------------


def test_redispatch_through_own_z3_safe_and_refuted(tmp_path) -> None:
    # imported obligations are ordinary I4s: the vendor pipeline is never
    # consulted - the shared-subset VCs re-dispatch through UVIL's pinned z3
    safe = _import_entry("generated/gen_add_comm.st").obligations[0]
    refutable = _import_entry("generated/gen_refute_double.st").obligations[0]
    result = run_check([safe, refutable], backend="z3", timeout_ms=5000)
    assert [o.status for o in result.obligations] == ["discharged", "refuted"]
    assert result.run is not None
    assert result.run.tool.name == "z3"  # NOT strata
    assert len(result.counterexamples) == 1  # the refutation carries a witness

    record_check(result, ContentStore(tmp_path / "store"), Ledger(tmp_path / "ledger.jsonl"))
    (entry,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entry.attestation is not None
    assert entry.attestation.tool == "z3"  # the G1 names UVIL's own backend


# --- vendor verify plumbing via a stub binary (no Strata needed) ----------------------


@pytest.fixture
def strata_stub(tmp_path: Path) -> Path:
    """A stub binary standing in for the pinned Strata-CLI.

    Platform-aware: a `.cmd` batch file on Windows (CreateProcess runs it via
    cmd.exe), a `#!/bin/sh` script with the exec bit on POSIX — `subprocess`
    execs the binary directly (no shell), so a shebang-less `.cmd` would fail
    there with `PermissionError` (CI: macOS/ubuntu). Both flavors emit the
    same verbatim lines the vendor-verdict assertions consume."""
    vendor_banner = "Strata-CLI (stub) commit " + PINNED_STRATA_COMMIT[:12]
    verify_banner = "[verify] 1 task, 1 task completed: verification succeeded"
    if sys.platform == "win32":
        stub = tmp_path / "strata-stub.cmd"
        stub.write_text(
            f"@echo off\r\necho {vendor_banner}\r\necho {verify_banner}\r\n",
            encoding="utf-8",
        )
    else:
        stub = tmp_path / "strata-stub.sh"
        stub.write_text(
            f'#!/bin/sh\necho "{vendor_banner}"\necho "{verify_banner}"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    return stub


def test_vendor_verdict_is_opaque_payload_never_a_guarantee(
    tmp_path, strata_stub, monkeypatch
) -> None:
    from typer.testing import CliRunner

    from uvil.artifacts import Proof
    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(STRATA_ENV_VAR, str(strata_stub))
    runner = CliRunner()
    runner.invoke(app, ["init"])

    artifact = tmp_path / "gen_add_comm.st"
    artifact.write_text(
        (STRATA_CORPUS / "generated" / "gen_add_comm.st").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["import-strata", str(artifact), "--vendor-verify"])
    assert result.exit_code == 0, result.output

    # the vendor verdict travels verbatim as an opaque I5 payload
    store = ContentStore(tmp_path / ".uvil")
    proofs = []
    for obj in sorted(store.objects.glob("*/*")):
        try:
            model = store.get_artifact(f"uvil:proof@1:{obj.name}")
        except Exception:
            continue
        proofs.append(model)
    assert len(proofs) == 1
    (proof,) = proofs
    assert isinstance(proof, Proof)
    assert proof.payload.format == VENDOR_PAYLOAD_FORMAT
    assert proof.checker.independent is False
    assert "verification succeeded" in (proof.payload.inline or "")
    # and it is NEVER a guarantee: no ledger entry was appended by the import
    ledger = Ledger(tmp_path / ".uvil" / "ledger.jsonl")
    assert ledger.entries() == []


def test_vendor_verify_skips_cleanly_without_strata(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(STRATA_ENV_VAR, raising=False)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    artifact = tmp_path / "gen_add_id.st"
    artifact.write_text(
        (STRATA_CORPUS / "generated" / "gen_add_id.st").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["import-strata", str(artifact), "--vendor-verify"])
    assert result.exit_code == 0, result.output
    assert "vendor verify skipped" in result.output


def test_import_strata_out_dir(tmp_path, strata_stub, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.setenv(STRATA_ENV_VAR, str(strata_stub))
    runner = CliRunner()
    artifact = tmp_path / "gen_refute_bound.st"
    artifact.write_text(
        (STRATA_CORPUS / "generated" / "gen_refute_bound.st").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = runner.invoke(app, ["import-strata", str(artifact), "--out", str(out)])
    assert result.exit_code == 0, result.output
    written = sorted(p.name for p in out.iterdir())
    assert any(".program." in n for n in written)
    assert any(".specification." in n for n in written)
    assert any(".obligation." in n for n in written)
