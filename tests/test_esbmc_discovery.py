"""ESBMC discovery pins: the v8.5 CLI/output surface, pinned by live probes.

These tests run the pinned binary on tiny harnesses and assert the exact
behaviors `backend.py`/`cex.py` rely on. They self-skip when ESBMC is absent
(CI runners); a divergence between the pin and a future binary fails HERE,
before any verdict mapping could silently drift.

Pinned findings (ESBMC 8.5.0, esbmc-windows.zip of release tag v8.5):
- `esbmc --version` reports "ESBMC version 8.5.0 ...";
- success prints `VERIFICATION SUCCESSFUL` and exits 0; a violated property
  prints `VERIFICATION FAILED` and exits 1; unparsable C exits nonzero with
  `PARSING ERROR` and no verdict line;
- `--generate-json-report` writes `report.json` (process CWD) on a violation
  and NOTHING on success; the report is an array of results with `steps[]`
  of type assignment/violation/assert/assume;
- `--timeout` is UNIMPLEMENTED on Windows (the adapter enforces budgets via
  the subprocess layer);
- `--bug-finding` does NOT exist in v8.5 (`unrecognised option`) - the
  documented multi-property mode is `--multi-property` (the plan's
  `[--bug-finding]` CLI option maps to it, recorded in the adapter docs).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from uvil.adapters.esbmc.backend import (
    PINNED_ESBMC,
    EsbmcBackend,
    EsbmcNotInstalled,
)

ESBMC_AVAILABLE = True
try:
    EsbmcBackend()
except EsbmcNotInstalled:
    ESBMC_AVAILABLE = False

SAFE = """#include <stdlib.h>
int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0 && x < 100) {
    assert(x < 100);
  }
  return 0;
}
"""

VIOLATED = """#include <stdlib.h>
int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 10) {
    assert(x <= 10);
  }
  return 0;
}
"""


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_version_pin_matches_binary() -> None:
    backend = EsbmcBackend()
    assert backend.esbmc_version == PINNED_ESBMC


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_verdict_strings_and_exit_codes(tmp_path: Path) -> None:
    backend = EsbmcBackend()
    safe = tmp_path / "safe.c"
    safe.write_text(SAFE, encoding="utf-8")
    proc = subprocess.run(
        [backend.executable, str(safe)], capture_output=True, text=True, check=False, timeout=120
    )
    assert proc.returncode == 0
    # ESBMC prints the verdict banner on stderr (discovery pin)
    assert "VERIFICATION SUCCESSFUL" in proc.stdout + proc.stderr

    bad = tmp_path / "bad.c"
    bad.write_text(VIOLATED, encoding="utf-8")
    proc = subprocess.run(
        [backend.executable, str(bad)], capture_output=True, text=True, check=False, timeout=120
    )
    assert proc.returncode == 1
    assert "VERIFICATION FAILED" in proc.stdout + proc.stderr


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_json_report_only_on_violation(tmp_path: Path) -> None:
    backend = EsbmcBackend()
    verdict = backend.run_source(SAFE, "safe.c", timeout_s=120)
    assert verdict.status == "verified"
    assert verdict.report_json is None

    verdict = backend.run_source(VIOLATED, "bad.c", timeout_s=120)
    assert verdict.status == "violated"
    assert verdict.report_json is not None
    report = json.loads(verdict.report_json)
    assert isinstance(report, list) and report
    (entry,) = report
    assert entry["status"] == "violation"
    types = {step["type"] for step in entry["steps"]}
    assert {"assignment", "violation"} <= types


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_timeout_flag_is_unimplemented_on_windows(tmp_path: Path) -> None:
    backend = EsbmcBackend()
    safe = tmp_path / "safe.c"
    safe.write_text(SAFE, encoding="utf-8")
    proc = subprocess.run(
        [backend.executable, "--timeout", "5s", str(safe)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode != 0
    assert "Timeout unimplemented" in proc.stdout + proc.stderr


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_bug_finding_flag_does_not_exist_in_v85(tmp_path: Path) -> None:
    # the plan drafted `[--bug-finding]` against an older surface; v8.5
    # rejects it (surprise -> pinned here, adapter uses --multi-property)
    backend = EsbmcBackend()
    safe = tmp_path / "safe.c"
    safe.write_text(SAFE, encoding="utf-8")
    proc = subprocess.run(
        [backend.executable, "--bug-finding", str(safe)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode != 0
    assert "unrecognised option" in proc.stdout + proc.stderr


@pytest.mark.skipif(not ESBMC_AVAILABLE, reason="esbmc not installed (pin: v8.5)")
def test_unparsable_c_maps_to_unknown_never_a_verdict() -> None:
    backend = EsbmcBackend()
    verdict = backend.run_source("int main(void) { int x = ; }", "broken.c", timeout_s=120)
    assert verdict.status == "unknown"
    assert verdict.report_json is None
