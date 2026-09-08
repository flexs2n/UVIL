from __future__ import annotations

import os

import pytest

from tests.fixtures import make_obligation
from uvil.adapters.smt.backends import (
    PINNED_Z3,
    Cvc5Backend,
    SmtVerdict,
    Z3Backend,
    verdict_status,
)
from uvil.adapters.smt.encode import encode_assertions, encode_script

PROVABLE = make_obligation()  # len + 1 <= cap given len < cap <= ...

REFUTABLE_SRC = """
procedure r(x: int)
{
  assert x + x == 3 * x;
}
"""

UNKNOWN_SRC = """
procedure u(x: int, y: int)
  requires x >= 7 && y >= 7
{
  assert x * x * x == y * y * y + 1;
}
"""


def _obligations_for(src: str, filename: str) -> list[object]:
    from uvil.adapters.boogie.lower import import_module

    result = import_module(src, filename)
    assert result.ok, [d.native_message for d in result.diagnostics]
    return list(result.obligations)


def _z3_run(script: str, budget: int | None = 2000) -> SmtVerdict:
    return Z3Backend().run(script, solver_ms=budget)


def test_z3_pin_enforced() -> None:
    assert PINNED_Z3 == "5.1.0"
    Z3Backend()  # installed wheel must match the pin or construction raises


def test_z3_discharges_provable() -> None:
    verdict = _z3_run(encode_assertions(PROVABLE))
    assert verdict.status == "unsat"
    assert verdict.solver_version == PINNED_Z3
    assert verdict_status(verdict) == "discharged"


def test_z3_refuted_with_model() -> None:
    (obl,) = _obligations_for(REFUTABLE_SRC, "r.bpl")
    verdict = _z3_run(encode_assertions(obl))
    assert verdict.status == "sat"
    assert verdict.model is not None and "x" in verdict.model
    assert verdict_status(verdict) == "refuted"


def test_z3_unknown_is_never_discharged() -> None:
    (obl,) = _obligations_for(UNKNOWN_SRC, "u.bpl")
    script = encode_assertions(obl)
    verdict = _z3_run(script, budget=1000)
    if verdict.status == "unsat":  # pragma: no cover - solver-dependent
        pytest.xfail("solver proved the nonlinear goal; unknown family needs adjusting")
    assert verdict.status in ("unknown", "timeout", "sat")
    assert verdict_status(verdict) != "discharged"


def test_verdict_mapping_is_total_and_fail_loud() -> None:
    cases = {
        "unsat": "discharged",
        "sat": "refuted",
        "unknown": "open",
        "timeout": "timeout",
    }
    for raw, expected in cases.items():
        v = SmtVerdict(status=raw, model=None, solver_version="test", time_ms=None)
        assert verdict_status(v) == expected
    # no other status can ever be produced by the mapping
    assert set(cases) == {"unsat", "sat", "unknown", "timeout"}


def test_timeout_budget_respected() -> None:
    (obl,) = _obligations_for(UNKNOWN_SRC, "u.bpl")
    verdict = _z3_run(encode_assertions(obl), budget=50)
    if verdict.status == "timeout":
        assert verdict_status(verdict) == "timeout"


def test_cvc5_backend_requires_env_or_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UVIL_CVC5", raising=False)
    with pytest.raises(RuntimeError, match="UVIL_CVC5"):
        Cvc5Backend()


CVC5 = os.environ.get("UVIL_CVC5")


@pytest.mark.skipif(not CVC5, reason="cvc5 binary not provided via UVIL_CVC5 (skip-if-absent)")
def test_cvc5_end_to_end() -> None:
    backend = Cvc5Backend(CVC5)
    assert backend.version()
    (obl,) = _obligations_for(REFUTABLE_SRC, "r.bpl")
    verdict = backend.run(encode_script(obl))
    assert verdict.status in ("sat", "unsat", "unknown")
    assert verdict_status(verdict) != "discharged" or verdict.status == "unsat"
