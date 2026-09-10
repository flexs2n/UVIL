from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from uvil.adapters.boogie.dafny import (
    PINNED_DAFNY,
    DafnyFrontend,
    DafnyNotInstalled,
    DafnyVersionMismatch,
    check_dafny_version,
    parse_dafny_version,
    subset_slice,
)


def test_parse_dafny_version() -> None:
    assert parse_dafny_version("Dafny 4.9.0.51921") == "4.9.0"
    assert parse_dafny_version("4.8.1") == "4.8.1"


def test_version_mismatch_fails_loud() -> None:
    with pytest.raises(DafnyVersionMismatch) as e:
        check_dafny_version("Dafny 4.8.1.00000")
    assert PINNED_DAFNY in str(e.value)


def test_version_match() -> None:
    assert check_dafny_version(f"Dafny {PINNED_DAFNY}.51921") == PINNED_DAFNY


def test_garbage_version_output_is_mismatch() -> None:
    with pytest.raises(DafnyVersionMismatch):
        parse_dafny_version("not a version")


def test_absent_binary_raises_not_installed() -> None:
    frontend = DafnyFrontend(executable="definitely-not-dafny-xyz")
    assert frontend.available() is False
    with pytest.raises(DafnyNotInstalled):
        frontend.translate(Path("whatever.dfy"))


DAFNY_ON_PATH = shutil.which("dafny") is not None

TINY_DFY = """
method VecPush(len: int, cap: int) returns (len': int)
  requires len < cap
  ensures len' == len + 1
{
  len' := len + 1;
  assert len' <= cap;
}
"""


@pytest.mark.skipif(not DAFNY_ON_PATH, reason="Dafny not installed (golden path is skip-if-absent)")
def test_full_dafny_pipeline(tmp_path: Path, snapshot: object) -> None:
    from uvil.adapters.boogie.dafny import subset_slice
    from uvil.adapters.boogie.lower import import_module
    from uvil.check.core import check

    dfy = tmp_path / "vec_push.dfy"
    dfy.write_text(TINY_DFY, encoding="utf-8")
    frontend = DafnyFrontend()
    assert frontend.version() == PINNED_DAFNY
    boogie_text = frontend.translate(dfy)
    # the translation is verbatim Dafny output: the user implementation is there
    assert "implementation " in boogie_text
    # the subset slice extracts the user procedure (drop count measured)
    sliced, dropped = subset_slice(boogie_text)
    assert dropped > 0  # the memory-model boilerplate is counted, never hidden
    result = import_module(sliced, filename="vec_push.dfy")
    # whatever the pinned Dafny emits must be loud: obligations or I7 diagnostics
    assert result.ok or result.diagnostics
    if result.ok and result.obligations:
        checked = check(result.obligations, backend="z3")
        assert checked.run is not None
        # the WP VCG proves the in-bounds push under the Dafny contract
        assert all(v.status == "discharged" for v in checked.run.verdicts)
        payload = [o.model_dump_json() for p in result.procedures.values() for o in p.obligations]
        assert payload == snapshot  # type: ignore[operator]


def test_subset_slice_is_deterministic() -> None:
    text = (
        "procedure P(x#0: int);\n"
        "  free requires 0 == $FunctionContextHeight;\n"
        "  requires x#0 >= 0;\n"
        "  modifies $Heap;\n"
        'implementation {:verboseName "P"} Impl$$_module.__default.P(x#0: int)\n'
        "{\n"
        "  var $_ModifiesFrame: [ref,Field]bool;\n"
        "  $_ModifiesFrame := (lambda $o: ref, $f: Field :: true);\n"
        "  x#0 := x#0 + 1;\n"
        "  assert x#0 >= 1;\n"
        "}\n"
    )
    sliced, dropped = subset_slice(text)
    assert "procedure" in sliced
    assert "requires x_0 >= 0;" in sliced
    assert "$Heap" not in sliced and "$_ModifiesFrame" not in sliced
    assert "assert x_0 >= 1;" in sliced
    assert "implementation " not in sliced
    assert dropped == 4  # free-requires, modifies, frame var, lambda assign
    again, dropped_again = subset_slice(text)
    assert (sliced, dropped) == (again, dropped_again)
