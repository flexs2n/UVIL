"""D1 verified-translator tests: preservation + cross-language parity.

- (no lean) the Python mirror's subset guards and s-expression format;
- (live lean) the pinned kernel accepts lean/UVIL/Core.lean (the preservation
  proof compiles) and the D1 evidence artifact records honestly
  (kernel-checked I9 + G1, idempotent);
- (live lean + built runner) Python <-> Lean parity over the s-expression
  fixture format through the `uvil-translate-prove` runner - the runner is
  built by `cd lean && lake build UVIL uvil-translate-prove` and is
  skip-if-absent.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from uvil.adapters.lean.backend import TOOLCHAIN_ID, LeanBackend, LeanNotInstalled
from uvil.artifacts.terms import Term, const, t_add, t_mul, t_sub, var
from uvil.artifacts.translation import Translation
from uvil.ledger import Ledger
from uvil.store import ContentStore
from uvil.translate import encode_lia, eval_term, fixture_line, interp, parse_env_line, to_sexpr


def t_intdiv(a: Term, b: Term) -> Term:
    return Term(op="intdiv", args=[a, b])


def t_mod(a: Term, b: Term) -> Term:
    return Term(op="mod", args=[a, b])


def t_neg(a: Term) -> Term:
    return Term(op="neg", args=[a])


REPO_ROOT = Path(__file__).resolve().parent.parent
LEAN_DIR = REPO_ROOT / "lean"
CORE_LEAN = LEAN_DIR / "UVIL" / "Core.lean"

RUNNER = (
    LEAN_DIR
    / ".lake"
    / "build"
    / "bin"
    / ("uvil-translate-prove.exe" if os.name == "nt" else "uvil-translate-prove")
)


def _lean_available() -> bool:
    try:
        LeanBackend()
        return True
    except LeanNotInstalled:
        return False


LEAN_OK = _lean_available()


def _term() -> Term:
    return t_add(var("x"), const(3))


# --- Python mirror (no lean needed) ---------------------------------------------------


def test_encode_lia_guards() -> None:
    # mul with a literal factor is in; both symbolic is out
    assert encode_lia(t_mul(var("x"), const(3))) is not None
    assert encode_lia(t_mul(const(3), var("x"))) is not None
    assert encode_lia(t_mul(var("x"), var("y"))) is None
    # div/mod require a positive constant divisor
    assert encode_lia(t_intdiv(var("x"), const(4))) is not None
    assert encode_lia(t_intdiv(var("x"), const(0))) is None
    assert encode_lia(t_intdiv(var("x"), const(-4))) is None
    assert encode_lia(t_mod(var("x"), const(4))) is not None
    assert encode_lia(t_mod(var("x"), var("d"))) is None
    # neg lifts to 0 - x
    neg = encode_lia(t_neg(var("x")))
    assert neg is not None and neg.kind == "sub" and neg.c == 0


def test_encode_lia_mul_normalizes_literal_to_front() -> None:
    # the commuted factor becomes mulLit c e (semantics unchanged)
    a = encode_lia(t_mul(const(3), var("x")))
    b = encode_lia(t_mul(var("x"), const(3)))
    assert a is not None and b is not None
    assert a.kind == "mulLit" and b.kind == "mulLit"
    assert a.c == b.c == 3
    env = {"x": 7}
    assert interp(a, env) == interp(b, env) == 21


def test_interp_and_eval_agree_python_side() -> None:
    terms_envs = [
        (t_add(var("x"), const(3)), {"x": 5}),
        (t_sub(var("x"), const(7)), {"x": -1}),
        (t_neg(t_add(var("x"), const(2))), {"x": 5}),
        (t_intdiv(var("x"), const(4)), {"x": 9}),
        (t_mod(var("x"), const(3)), {"x": 8}),
        (t_mul(const(3), const(4)), {}),
    ]
    for term, env in terms_envs:
        encoded = encode_lia(term)
        assert encoded is not None, to_sexpr(term)
        assert interp(encoded, env) == eval_term(term, env)


def test_sexpr_format_round_trip_shape() -> None:
    term = t_add(t_mul(var("x"), const(3)), t_sub(var("y"), t_neg(const(2))))
    text = to_sexpr(term)
    assert text == "(add (mul (var x) (const 3)) (sub (var y) (neg (const 2))))"
    # the env suffix parses back to the same mapping
    env = parse_env_line("x=7, y=-2")
    assert env == {"x": 7, "y": -2}
    assert fixture_line(term, env).startswith(text + " | ")


# --- the pinned kernel accepts the preservation proof (live lean) ---------------------


@pytest.mark.skipif(not LEAN_OK, reason="lean not installed (elan absent)")
def test_pinned_kernel_accepts_core_lean() -> None:
    backend = LeanBackend()
    core_text = CORE_LEAN.read_text(encoding="utf-8")
    verdict = backend.check_batch([core_text])[0]
    assert verdict.status == "attested", verdict.native_output


@pytest.mark.skipif(not LEAN_OK, reason="lean not installed (elan absent)")
def test_translator_evidence_kernel_checked(tmp_path) -> None:
    from uvil.check.translator import (
        CORE_TARGET_KIND,
        translator_evidence,
        translator_kernel_hash,
    )

    store = ContentStore(tmp_path / "store")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ref = translator_evidence(store, ledger)
    model = store.get_artifact(ref)
    assert isinstance(model, Translation)
    assert model.soundness_discipline == "kernel-checked"
    assert model.target_kind == CORE_TARGET_KIND
    assert model.mapping
    assert model.mapping[0]["preservation"] == "Uvil.Term.encodeLia_preserves"

    (entry,) = ledger.entries()
    assert entry.guarantee_class == "G1"
    assert entry.attestation is not None
    core_text = CORE_LEAN.read_text(encoding="utf-8")
    assert entry.attestation.kernel_hash == translator_kernel_hash(core_text)
    assert ledger.verify() == []
    # recorded ONCE: re-emitting the same evidence is idempotent at the CAS
    ref2 = translator_evidence(store, Ledger(tmp_path / "ledger2.jsonl"))
    assert ref2 == ref


# --- cross-language parity (live lean + built runner) ----------------------------------


RUNNER_AVAILABLE = RUNNER.exists()


def _parity_fixtures() -> list[tuple[Term, dict[str, int]]]:
    return [
        (t_add(var("x"), const(3)), {"x": 5}),
        (t_sub(var("x"), const(7)), {"x": -1}),
        (t_neg(t_add(var("x"), const(2))), {"x": 5}),
        (t_intdiv(var("x"), const(4)), {"x": 9}),
        (t_mod(var("x"), const(3)), {"x": 8}),
        (t_mul(const(3), const(4)), {}),
        (t_mul(var("x"), const(-2)), {"x": 6}),
        (
            t_sub(t_add(t_mul(var("x"), const(2)), var("y")), t_neg(const(1))),
            {"x": 3, "y": 4},
        ),
    ]


@pytest.mark.skipif(
    not LEAN_OK or not RUNNER_AVAILABLE,
    reason="lean runner not built (cd lean && lake build UVIL uvil-translate-prove)",
)
def test_python_lean_parity_over_fixture_format() -> None:
    fixtures = _parity_fixtures()
    lines = "\n".join(fixture_line(t, e) for t, e in fixtures)
    proc = subprocess.run(
        [str(RUNNER)],
        input=lines,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        encoding="utf-8",
    )
    outs = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(outs) == len(fixtures), proc.stdout + proc.stderr
    for (term, env), out in zip(fixtures, outs, strict=True):
        encoded = encode_lia(term)
        assert encoded is not None
        expected = interp(encoded, env)
        assert out == f"some {expected} {expected}", (to_sexpr(term), out)


@pytest.mark.skipif(
    not LEAN_OK or not RUNNER_AVAILABLE,
    reason="lean runner not built (cd lean && lake build UVIL uvil-translate-prove)",
)
def test_lean_runner_rejects_out_of_subset_terms() -> None:
    fixture = fixture_line(t_mul(var("x"), var("y")), {"x": 2, "y": 7})
    proc = subprocess.run(
        [str(RUNNER)],
        input=fixture,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        encoding="utf-8",
    )
    assert proc.stdout.strip() == "none"


def test_preservation_lemma_name_is_stable_in_core_lean() -> None:
    # the evidence artifact and the Lean file must agree on the lemma name
    from uvil.check.translator import PRESERVATION_LEMMA

    core_text = CORE_LEAN.read_text(encoding="utf-8")
    local_name = PRESERVATION_LEMMA.removeprefix("Uvil.")
    assert f"theorem {local_name} :" in core_text


def test_toolchain_pin_consistent() -> None:
    assert TOOLCHAIN_ID == "leanprover/lean4:v4.33.1"
    assert (LEAN_DIR / "lean-toolchain").read_text(encoding="utf-8").strip() == TOOLCHAIN_ID
