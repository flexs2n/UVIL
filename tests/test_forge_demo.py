"""Forge-demo pipeline test: one artifact set through model checking (ESBMC)
+ deduction (z3) + theorem proving (Lean twin; Isabelle twin behind its
skip-if-absent pin) - the M4 exit criterion as a live test.

Verifies the committed example files stay coherent with the documented
pipeline (examples/forge_on_uvil/README.md): the C bug is real (ESBMC
violates), the distilled encoding is refuted, the repaired encoding
discharges, and the discharged sequent's Lean twin attests (G1) - all
through the committed CLI, no bespoke glue.
"""

from __future__ import annotations

import pytest

from uvil.adapters.boogie.lower import import_module
from uvil.adapters.esbmc.backend import EsbmcBackend, EsbmcNotInstalled
from uvil.adapters.esbmc.import_c import import_c
from uvil.adapters.lean.backend import LeanBackend, LeanNotInstalled
from uvil.check.core import check as run_check
from uvil.check.lean import check_lean

DEMO = __import__("pathlib").Path(__file__).resolve().parent.parent / "examples" / "forge_on_uvil"

ESBMC_AVAILABLE = True
try:
    EsbmcBackend()
except EsbmcNotInstalled:
    ESBMC_AVAILABLE = False

LEAN_AVAILABLE = True
try:
    LeanBackend()
except LeanNotInstalled:
    LEAN_AVAILABLE = False


def test_distilled_encoding_is_refuted_and_repair_discharges() -> None:
    buggy = import_module((DEMO / "clamp.bpl").read_text(encoding="utf-8"), "clamp.bpl")
    assert buggy.ok
    fixed = import_module((DEMO / "clamp_fixed.bpl").read_text(encoding="utf-8"), "clamp_fixed.bpl")
    assert fixed.ok

    checked_buggy = run_check(list(buggy.obligations), backend="z3", timeout_ms=5000)
    assert checked_buggy.obligations[0].status == "refuted"
    assert len(checked_buggy.counterexamples) == 1  # the I6 witness travels

    checked_fixed = run_check(list(fixed.obligations), backend="z3", timeout_ms=5000)
    assert checked_fixed.obligations[0].status == "discharged"


@pytest.mark.skipif(not LEAN_AVAILABLE, reason="lean not installed (elan absent)")
def test_repaired_sequent_lean_twin_attests() -> None:
    fixed = import_module((DEMO / "clamp_fixed.bpl").read_text(encoding="utf-8"), "clamp_fixed.bpl")
    result = check_lean(list(fixed.obligations))
    assert result.obligations[0].status == "discharged"
    assert len(result.proofs) == 1
    assert result.run is not None and result.run.verdicts[0].status == "discharged"


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_esbmc_finds_the_c_bug() -> None:
    harness = import_c((DEMO / "clamp.c").read_text(encoding="utf-8"), "clamp.c")
    assert harness.ok
    backend = EsbmcBackend()
    verdict = backend.run_source(
        (DEMO / "clamp.c").read_text(encoding="utf-8"), "clamp.c", timeout_s=60
    )
    assert verdict.status == "violated"
    assert verdict.report_json is not None
    # the violated property is the value-preservation assertion (line 17)
    from uvil.adapters.esbmc.cex import parse_report_steps

    steps = parse_report_steps(verdict.report_json)
    assert any(s.vars.get("property") == "assertion c == x || c == 10" for s in steps)
