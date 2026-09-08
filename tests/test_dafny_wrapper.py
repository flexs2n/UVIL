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
}
"""


@pytest.mark.skipif(not DAFNY_ON_PATH, reason="Dafny not installed (golden path is skip-if-absent)")
def test_full_dafny_pipeline(tmp_path: Path, snapshot: object) -> None:
    from uvil.adapters.boogie.lower import import_module

    dfy = tmp_path / "vec_push.dfy"
    dfy.write_text(TINY_DFY, encoding="utf-8")
    frontend = DafnyFrontend()
    assert frontend.version() == PINNED_DAFNY
    boogie_text = frontend.translate(dfy)
    result = import_module(boogie_text, filename="vec_push.dfy")
    # Real Dafny output may fall outside the M1 subset; whatever happens must be
    # loud: either obligations, or I7 parse diagnostics with verbatim lines.
    assert result.ok or result.diagnostics
    if result.ok:
        payload = [o.model_dump_json() for p in result.procedures.values() for o in p.obligations]
        assert payload == snapshot  # type: ignore[operator]
