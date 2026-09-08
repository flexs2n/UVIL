"""Lean toolchain discovery tests (live compiles, skip-if-absent).

These pin the `omega` behavior of the pinned toolchain (`lean/lean-toolchain`)
that the encoder in `uvil.adapters.lean.encode` relies on. Without elan on
PATH (or `~/.elan/bin`), the whole module self-skips - the Dafny precedent.

Findings (leanprover/lean4:v4.33.1):
- linear Int arithmetic incl. conjunctive/disjunctive comparison hypotheses: OK
- Bool atoms: direct `p = true`/`p = false` facts OK; conjunctions of Bool
  atoms and general Bool-Bool equality NOT omega-provable
- `ite` on Int operands: OK
- Int `/`/`%` are FLOORED (`(-7)/2 = -4`), matching SMT-LIB Euclidean
  div/mod for positive divisors (identity shape discharges)
- quantified hypotheses: simple comparison bodies OK; implication/conjunction
  spines inside quantifiers NOT
- Real: omega fails loud
- cold start ~4s, warm ~1s: ~25 theorems/file amortizes it
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLCHAIN_PIN = REPO_ROOT / "lean" / "lean-toolchain"


def _lean_executable() -> str | None:
    found = shutil.which("lean")
    if found:
        return found
    local = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".elan" / "bin" / "lean.exe"
    return str(local) if local.exists() else None


LEAN = _lean_executable()

pytestmark = pytest.mark.skipif(LEAN is None, reason="lean not installed (elan absent)")


def _compile_ok(source: str) -> tuple[bool, str]:
    """Compile a standalone .lean file; returns (exit0, combined_output).

    Runs under the repo's `lean-toolchain` pin (via ELAN_TOOLCHAIN, since the
    temp dir has no toolchain file and no default toolchain is configured).
    """
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False, encoding="utf-8") as f:
        f.write(source)
        path = Path(f.name)
    env = dict(os.environ)
    if TOOLCHAIN_PIN.exists():
        # the caller's environment may have no default toolchain configured;
        # the elan shim honors ELAN_TOOLCHAIN for exactly this case
        env["ELAN_TOOLCHAIN"] = TOOLCHAIN_PIN.read_text(encoding="utf-8").strip()
    try:
        proc = subprocess.run(
            [LEAN, path.name],
            capture_output=True,
            text=True,
            check=False,
            cwd=path.parent,
            timeout=120,
            env=env,
        )
        return proc.returncode == 0, (proc.stdout + proc.stderr)
    finally:
        path.unlink(missing_ok=True)


def _compile_fails(source: str) -> str:
    ok, output = _compile_ok(source)
    assert not ok, f"expected compile failure but got exit-0\n{output}"
    return output


def test_toolchain_pin_file_exists() -> None:
    assert TOOLCHAIN_PIN.exists(), "lean/lean-toolchain pin missing (step 0)"
    pin = TOOLCHAIN_PIN.read_text(encoding="utf-8").strip()
    assert pin.startswith("leanprover/lean4:v")


def test_discovery_linear_int_props() -> None:
    ok, output = _compile_ok(
        """
theorem p1 (x y : Int) (h : x + y = 7) : x + 1 + y = 8 := by omega
theorem p2 (x : Int) (h : x ≥ 2 ∧ x ≤ 2) : x = 2 := by omega
theorem p3 (x : Int) (h : x ≥ 2 ∨ x ≤ -2) : ¬(x = 0) := by omega
theorem p4 (a b : Int) (h : a ≥ -5 ∧ b ≥ 3) : a + b = b + a := by omega
theorem p5 (x y : Int) (h1 : x ≥ 0) (h2 : y ≥ 0) : x + y ≥ 0 := by omega
"""
    )
    assert ok, output


def test_discovery_bool_atoms_are_direct_literal_facts_only() -> None:
    """Direct `p = true` facts discharge; conjunctions of Bool atoms and
    general Bool-Bool equality do NOT (the encoder fails loud on those)."""
    ok, output = _compile_ok(
        """
theorem b1 (p : Bool) (h : p = true) : p = true := by omega
theorem b2 (x : Int) (p : Bool) (h : p = false) : x = x := by omega
"""
    )
    assert ok, output
    output = _compile_fails(
        "theorem b3 (p q : Bool) (h : p = true ∧ q = true) : p = true := by omega\n"
    )
    assert "omega" in output
    output = _compile_fails("theorem b4 (p q : Bool) : p = q ∨ q = p := by omega\n")
    assert "omega" in output


def test_discovery_quantifiers_over_int() -> None:
    ok, output = _compile_ok(
        """
theorem q1 (n : Int) (h : ∀ i : Int, i < n) : n = n := by omega
theorem q2 (n : Int) (h : ∃ j : Int, j = 3) : n = n := by omega
theorem q3 : ∀ (a b : Int), a + b = b + a := by omega
"""
    )
    assert ok, output


def test_discovery_quantified_hypotheses_with_boolean_spines_fail() -> None:
    """omega does NOT discharge implication/conjunction spines inside
    quantified hypotheses - the encoder restricts quantifier bodies to single
    comparisons instead of emitting doomed theorems."""
    for src in (
        "theorem q4 (n : Int) (h : ∀ i : Int, 0 ≤ i → i < n → i ≤ 0) : 5 ≤ n → n = 5 := by omega\n",
        "theorem q5 (n : Int) (h : ∀ i : Int, 0 ≤ i ∧ i < n → i ≤ 0) : 5 ≤ n → n = 5 := by omega\n",
    ):
        output = _compile_fails(src)
        assert "omega" in output


def test_discovery_ite_on_int_operands() -> None:
    """Decides minmax/abs-bound inclusion in the slice."""
    ok, output = _compile_ok(
        """
theorem i1 (a b : Int) : (if a < b then a else b) ≤ b := by omega
theorem i2 (x k : Int) (h : x ≥ 0 ∧ x ≤ k) :
    (if x < 0 then -x else x) ≤ k := by omega
"""
    )
    assert ok, output


def test_discovery_int_division_is_floored_matching_smtlib() -> None:
    """Lean 4.33 Int `/`/`%` are floored: `(-7)/2 = -4`, `(-7)%2 = 1` -
    the SMT-LIB Euclidean values. The positive-divisor identity shape
    (the constant-pin emission form) discharges by omega."""
    ok, output = _compile_ok(
        """
example : (-7 : Int) / 2 = -4 := by decide
example : (-7 : Int) % 2 = 1 := by decide
theorem d1 (a : Int) : a / 7 * 7 + a % 7 = a := by omega
theorem d2 (a : Int) : a / 3 * 3 + a % 3 = a := by omega
"""
    )
    assert ok, output


def test_discovery_real_rejected_by_omega() -> None:
    output = _compile_fails("theorem r1 (r : Rat) (h : r + r = 2 * r) : r = r := by omega\n")
    assert "omega" in output


def test_discovery_cold_start_timing_bounds_batching_budget() -> None:
    """A ~20-theorem batch file must compile in well under a minute so ~25
    theorems/file amortizes the cold start (M3 batching budget)."""
    theorems = "\n".join(
        f"theorem t{i} (a b : Int) (h : a ≥ {i}) : a + b = b + a := by omega" for i in range(20)
    )
    start = time.perf_counter()
    ok, output = _compile_ok(theorems)
    elapsed = time.perf_counter() - start
    assert ok, output
    assert elapsed < 60, f"20-theorem batch took {elapsed:.1f}s - batching budget blown"
