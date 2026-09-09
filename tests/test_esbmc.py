"""ESBMC adapter tests: verdict discipline, C import, corpus, CLI.

Structure mirrors test_lean_check.py:
- (no esbmc) the total verdict mapping, import_c subset behavior, corpus
  manifest coherence + regeneration determinism, render dispatch, and the
  record_esbmc G0/G1 discipline;
- (live, skip-if-absent) backend verdicts, check_esbmc wiring with I6 traces,
  and the CLI round trip.

Discovery pins live in test_esbmc_discovery.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uvil.adapters.esbmc.backend import (
    ESBMC_RELEASE_TAG,
    PINNED_ESBMC,
    EsbmcBackend,
    EsbmcNotInstalled,
    EsbmcVerdict,
    esbmc_status,
)
from uvil.adapters.esbmc.cex import ESBMC_TRACE_FORMAT, parse_report_steps
from uvil.adapters.esbmc.import_c import import_c
from uvil.check.esbmc import CHarness, EsbmcCheckResult, check_esbmc, record_esbmc
from uvil.ledger import Ledger
from uvil.render import to_backend_render
from uvil.store import ContentStore

REPO_ROOT = Path(__file__).resolve().parent.parent
C_CORPUS = REPO_ROOT / "corpora" / "c"

SAFE_SRC = """#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0 && x < 100) {
    assert(x < 100);
  }
  return 0;
}
"""

VIOLATED_SRC = """#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 10) {
    assert(x <= 10);
  }
  return 0;
}
"""


def _verdict(status: str) -> EsbmcVerdict:
    return EsbmcVerdict(
        status=status,  # type: ignore[arg-type]
        esbmc_version=PINNED_ESBMC,
        time_ms=None,
        raw_output="",
        report_json=None,
    )


ESBMC_AVAILABLE = True
try:
    EsbmcBackend()
except EsbmcNotInstalled:
    ESBMC_AVAILABLE = False


# --- the total verdict mapping (no esbmc needed) -----------------------------------


def test_verdict_mapping_is_total_and_never_upgrades() -> None:
    # model-checking results NEVER discharge a deductive obligation and NEVER
    # refute one (R1): verified/violated/unknown keep the obligation open
    assert esbmc_status(_verdict("verified")) == "open"
    assert esbmc_status(_verdict("violated")) == "open"
    assert esbmc_status(_verdict("unknown")) == "open"
    assert esbmc_status(_verdict("timeout")) == "timeout"
    for status in ("verified", "violated", "unknown", "timeout"):
        assert esbmc_status(_verdict(status)) not in ("discharged", "refuted", "vacuous")


def test_pin_is_the_pinned_release() -> None:
    assert PINNED_ESBMC == "8.5.0"
    assert ESBMC_RELEASE_TAG == "v8.5"


# --- import_c: the documented subset (no esbmc needed) ------------------------------


def test_import_safe_harness_sequent() -> None:
    from uvil.artifacts.terms import to_smt

    result = import_c(SAFE_SRC, "safe.c")
    assert result.ok
    (harness,) = result.harnesses
    assert harness.program.language == "c"
    assert harness.program.symbol == "main"
    assert harness.program.semantics_model == "model:esbmc-goto.v1"
    assert harness.obligations
    (obl,) = harness.obligations
    assert obl.origin_backend == "esbmc-c"
    assert obl.target_profile == "uvil.esbmc-c@1"
    assert obl.theories == ["uvil.core.int@1", "uvil.core.bool@1"]
    assert [to_smt(c) for c in obl.sequent.context] == ["(and (>= x 0) (< x 100))"]
    assert to_smt(obl.sequent.goal) == "(< x 100)"
    assert obl.sequent.var_sorts == {"x": "Int"}
    # the contract carries the assertion as an ensures
    assert harness.spec.contracts.ensures == [obl.sequent.goal]


def test_import_paths_fork_and_unroll() -> None:
    from uvil.artifacts.terms import to_smt

    src = """int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0) {
    assert(x >= 0);
  } else {
    assert(x < 0);
  }
  int s = 0;
  for (int i = 0; i < 4; i++) {
    s = s + i;
  }
  assert(s == 6);
  return 0;
}
"""
    result = import_c(src, "fork.c")
    assert result.ok, [d.native_message for d in result.diagnostics]
    goals = [to_smt(o.sequent.goal) for o in result.obligations]
    assert goals[0] == "(>= x 0)"
    assert goals[1] == "(< x 0)"
    # path forking continues after the merge: the final assert yields one
    # obligation per live path (both carry the unrolled loop context)
    assert len(goals) == 4
    assert goals[2].startswith("(= (+ ") and goals[2].endswith(" 6)")
    assert goals[3].startswith("(= (+ ") and goals[3].endswith(" 6)")
    last = result.obligations[-1]
    # 1 branch condition + 4 unrolled loop conditions
    assert len(last.sequent.context) == 5
    assert all(to_smt(c).startswith("(< ") for c in last.sequent.context[1:])


@pytest.mark.parametrize(
    ("src", "label"),
    [
        ("int main(void) { while (1) { } }", "while"),
        ("int main(void) { int a[3]; a[0] = 1; }", "array-index"),
        ("int main(void) { int *p = 0; *p = 1; }", "pointer-deref"),
        ("int main(void) { int x; int y = x + 1; }", "uninitialized-read"),
        ("int main(void) { for (int i = 0; i < 100; i++) { } }", "unroll-budget"),
        ("int main(void) { int x = 1; int y = f(x); }", "function-call"),
        ("int main(void) { int x = 1; if (x + 1) { } }", "bare-arith-condition"),
        ("int main(void) { int x = 1; int y = x > 0; }", "comparison-as-value"),
        ("int f(void) { return 1; } int main(void) { return 0; }", "not-a-main-harness"),
    ],
)
def test_import_out_of_subset_fails_loud_with_verbatim_line(src: str, label: str) -> None:
    result = import_c(src, "out.c")
    assert not result.ok, label
    (diag,) = result.diagnostics
    assert diag.kind == "parse"
    assert diag.obligation_ref is None
    # the verbatim source line is preserved
    assert any(line.strip() in diag.native_message for line in src.splitlines())
    assert result.harnesses == []


def test_import_nondet_reassignment_gets_a_fresh_symbol() -> None:
    from uvil.artifacts.terms import to_smt

    src = """int main(void) {
  int x = __VERIFIER_nondet_int();
  int y = x;
  x = __VERIFIER_nondet_int();
  assert(y != x);
  return 0;
}
"""
    result = import_c(src, "nondet.c")
    assert result.ok
    (obl,) = result.obligations
    # the first nondet value keeps symbol `x` (y aliases it); the
    # reassignment introduces the fresh symbol `x_2`
    assert sorted(obl.sequent.var_sorts) == ["x", "x_2"]
    assert to_smt(obl.sequent.goal) == "(distinct x x_2)"


def test_import_cprover_assert_form() -> None:
    src = (
        'int main(void) {\n  int x = 3;\n  __CPROVER_assert(x > 0, "x positive");\n  return 0;\n}\n'
    )
    result = import_c(src, "cp.c")
    assert result.ok
    assert len(result.obligations) == 1


def test_import_assertions_in_dead_code_are_not_obligations() -> None:
    src = """int main(void) {
  int x = 1;
  if (x > 5) {
    return 1;
  } else {
    return 0;
  }
  assert(x > 100);
  return 1;
}
"""
    # everything after the if/else is unreachable; the walk covers the two
    # branches and the trailing assert belongs to no live path
    result = import_c(src, "dead.c")
    assert result.ok
    assert result.obligations == []


# --- corpus (no esbmc needed) --------------------------------------------------------


def _manifest() -> dict:
    return json.loads((C_CORPUS / "expected.json").read_text(encoding="utf-8"))


def test_corpus_manifest_shape_and_size() -> None:
    manifest = _manifest()
    meta = manifest["meta"]
    assert meta["esbmc_pin"] == PINNED_ESBMC
    assert meta["release_tag"] == ESBMC_RELEASE_TAG
    expected = manifest["expected"]
    assert len(expected) >= 50
    families = {e["family"] for e in expected.values()}
    assert families == {"safe-assert", "overflow", "div-zero", "bounds", "pointer-heap", "deep"}
    for stem, entry in expected.items():
        assert entry["file"] == f"{stem}.c", stem
        assert entry["expected"] in ("verified", "violated", "timeout"), stem
        assert entry["import"] in ("obligations", "out-of-subset"), stem


def test_corpus_files_match_manifest() -> None:
    manifest = _manifest()
    on_disk = sorted(p.name for p in C_CORPUS.glob("*.c"))
    in_manifest = sorted(e["file"] for e in manifest["expected"].values())
    assert on_disk == in_manifest


def test_corpus_import_behavior_is_as_declared() -> None:
    for stem, entry in _manifest()["expected"].items():
        source = (C_CORPUS / entry["file"]).read_text(encoding="utf-8")
        result = import_c(source, entry["file"])
        if entry["import"] == "obligations":
            assert result.ok, stem
            assert result.obligations, stem
        else:
            assert not result.ok, stem
            assert all(d.kind == "parse" for d in result.diagnostics), stem
            assert not result.obligations, stem


def test_corpus_regeneration_is_deterministic() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import gen_c_corpus

    entries_a, meta_a = gen_c_corpus.build_corpus()
    entries_b, meta_b = gen_c_corpus.build_corpus()
    assert meta_a == meta_b
    assert entries_a == entries_b
    payload = gen_c_corpus.generate()
    assert payload == _manifest()


# --- render dispatch (no esbmc needed) ------------------------------------------------


def test_esbmc_trace_render_is_verbatim_report() -> None:
    report = '[{"status": "violation", "steps": []}]'
    states = parse_report_steps(report)
    assert states == []
    from tests.fixtures import make_trace_counterexample
    from uvil.artifacts.counterexample import BackendWitness

    cex = make_trace_counterexample("obl:x").model_copy(
        update={
            "backend_witness": BackendWitness(format=ESBMC_TRACE_FORMAT, payload=report),
            "trace": [],
        }
    )
    assert to_backend_render(cex) == report


def test_esbmc_trace_render_fails_loud_without_witness_payload() -> None:
    from tests.fixtures import make_trace_counterexample

    cex = make_trace_counterexample("obl:x")  # M2 pre-registered fixture: payload=None
    with pytest.raises(NotImplementedError, match="esbmc-trace"):
        to_backend_render(cex)


def test_report_steps_parse_to_trace_states() -> None:
    report = json.dumps(
        [
            {
                "status": "violation",
                "steps": [
                    {
                        "type": "assignment",
                        "assignment": {
                            "lhs": "x",
                            "rhs": "11",
                            "lhs_type": "signed",
                            "rhs_type": "signed",
                        },
                        "file": "bad.c",
                        "line": "4",
                        "function": "main",
                        "step_number": 0,
                    },
                    {
                        "type": "violation",
                        "assertion": {
                            "comment": "assertion x <= 10",
                            "guard": "0",
                            "violated": True,
                        },
                        "message": "assertion x <= 10",
                        "file": "bad.c",
                        "line": "6",
                        "function": "main",
                        "step_number": 1,
                    },
                    {
                        "type": "assume",
                        "message": "Assumption restriction",
                        "file": "bad.c",
                        "line": "9",
                        "function": "main",
                        "step_number": 2,
                    },
                ],
            }
        ]
    )
    states = parse_report_steps(report)
    assert [(s.vars, s.loc) for s in states] == [
        ({"x": "11"}, "bad.c:4:main"),
        ({"property": "assertion x <= 10"}, "bad.c:6:main"),
        ({}, "bad.c:9:main"),
    ]


# --- record_esbmc (no esbmc needed) ----------------------------------------------------


def _fabricated_run():
    from uvil.artifacts import Run
    from uvil.artifacts.run import ToolDescriptor, Verdict

    return Run(
        tool=ToolDescriptor(name="esbmc", version=PINNED_ESBMC, flags=[]),
        config={},
        verdicts=[Verdict(obligation_ref="uvil:obligation@1:" + "0" * 64, status="open")],
    )


def test_record_esbmc_rejects_runless_result(tmp_path) -> None:
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError, match="run"):
        record_esbmc(EsbmcCheckResult(), store, ledger)


def test_record_esbmc_zero_verified_appends_g0(tmp_path) -> None:
    # a run with no verified harness must not fabricate a guarantee (R1)
    result = EsbmcCheckResult()
    result.run = _fabricated_run()
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record_esbmc(result, store, ledger)
    assert refs
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G0"
    assert entry.attestation is not None
    assert entry.attestation.tool == "esbmc"
    assert "without guarantee" in (entry.attestation.detail or "")


def test_record_esbmc_g1_never_fabricates_kernel_hash(tmp_path) -> None:
    result = EsbmcCheckResult()
    result.run = _fabricated_run()
    result.run.verdicts[0] = result.run.verdicts[0].model_copy(
        update={"note": "model-checking: verified (bounded C semantics)"}
    )
    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    record_esbmc(result, store, ledger)
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G1"
    assert entry.attestation is not None
    assert entry.attestation.tool == "esbmc"
    assert entry.attestation.version == PINNED_ESBMC
    assert entry.attestation.kernel_hash is None  # no kernel participates
    assert "no cross-upgrade" in (entry.attestation.detail or "")
    assert ledger.verify() == []


# --- live backend + check_esbmc + CLI (skip-if-absent) ---------------------------------


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_backend_version_pin_enforced() -> None:
    backend = EsbmcBackend()
    assert backend.esbmc_version == PINNED_ESBMC


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_backend_verdicts_on_safe_and_violated() -> None:
    backend = EsbmcBackend()
    safe = backend.run_source(SAFE_SRC, "safe.c", timeout_s=60)
    assert safe.status == "verified"
    assert safe.report_json is None  # no report on success (discovery pin)
    assert "VERIFICATION SUCCESSFUL" in safe.raw_output

    violated = backend.run_source(VIOLATED_SRC, "violated.c", timeout_s=60)
    assert violated.status == "violated"
    assert violated.report_json is not None
    assert "VERIFICATION FAILED" in violated.raw_output


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_backend_maps_unparsable_c_to_unknown() -> None:
    backend = EsbmcBackend()
    verdict = backend.run_source("int main(void) { int x = ; }", "broken.c", timeout_s=60)
    assert verdict.status == "unknown"  # never upgraded


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_check_esbmc_violated_emits_trace_not_refutation() -> None:
    imported = import_c(VIOLATED_SRC, "violated.c")
    assert imported.ok
    (obl,) = imported.obligations
    result = check_esbmc([CHarness(source=VIOLATED_SRC, filename="violated.c", obligations=[obl])])
    assert result.run is not None
    assert result.run.tool.name == "esbmc"
    assert result.run.tool.version == PINNED_ESBMC
    (verdict,) = result.run.verdicts
    assert verdict.status == "open"  # model-checking never refutes (R1)
    assert verdict.note is not None and "model-checking: violated" in verdict.note
    assert result.obligations[0].status == "open"
    (cex,) = result.counterexamples
    assert cex.kind == "trace"
    assert cex.backend_witness is not None
    assert cex.backend_witness.format == "esbmc-trace"
    assert any("property" in s.vars for s in (cex.trace or []))
    (diag,) = result.diagnostics
    assert diag.kind == "unproved"
    assert "not a deductive refutation" in diag.native_message


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_check_esbmc_verified_keeps_obligation_open_with_g1(tmp_path) -> None:
    imported = import_c(SAFE_SRC, "safe.c")
    (obl,) = imported.obligations
    result = check_esbmc([CHarness(source=SAFE_SRC, filename="safe.c", obligations=[obl])])
    assert result.obligations[0].status == "open"  # never discharged by model checking
    assert not result.diagnostics
    assert not result.counterexamples

    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    refs = record_esbmc(result, store, ledger)
    for ref in refs:
        store.get_artifact(ref)
    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G1"
    assert "model-checking G1" in (entry.attestation.detail or "")  # type: ignore[union-attr]
    assert ledger.verify() == []


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_cli_check_esbmc_round_trip(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init"])
    safe = tmp_path / "safe.c"
    safe.write_text(SAFE_SRC, encoding="utf-8")
    violated = tmp_path / "violated.c"
    violated.write_text(VIOLATED_SRC, encoding="utf-8")

    result = runner.invoke(app, ["check-esbmc", str(safe), str(violated)])
    assert result.exit_code == 0, result.output
    assert "model-checking run record" in result.output

    # the violated harness's I6 trace is in the CAS and renders verbatim
    store = ContentStore(tmp_path / ".uvil")
    traces = []
    for obj in sorted(store.objects.glob("*/*")):
        try:
            model = store.get_artifact(f"uvil:counterexample@1:{obj.name}")
        except Exception:
            continue
        traces.append(model)
    assert any(
        t.kind == "trace"
        and t.backend_witness is not None
        and t.backend_witness.format == "esbmc-trace"
        for t in traces
    )


def test_cli_check_esbmc_skips_when_absent(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from uvil.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UVIL_ESBMC", str(tmp_path / "missing" / "esbmc.exe"))
    runner = CliRunner()
    runner.invoke(app, ["init"])
    safe = tmp_path / "safe.c"
    safe.write_text(SAFE_SRC, encoding="utf-8")
    result = runner.invoke(app, ["check-esbmc", str(safe)])
    assert result.exit_code == 0, result.output
    assert "skip" in result.output


def test_find_esbmc_env_override_missing_binary_is_skip_not_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UVIL_ESBMC", str(tmp_path / "missing" / "esbmc.exe"))
    with pytest.raises(EsbmcNotInstalled, match="UVIL_ESBMC"):
        EsbmcBackend()
