"""Shadow-set evaluation (R4) tests + `uvil shadows` CLI.

The operational semantics are pinned in `uvil.check.shadows` and exercised
here for all four probe outcomes: refute-ok, refute-vacuous, accept-ok,
accept-vacuous, plus the never-a-pass arms (unknown/timeout, opaque formula).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.fixtures import make_spec
from uvil.artifacts import Specification, artifact_id
from uvil.artifacts.spec import Contracts, ShadowHypothesis
from uvil.artifacts.terms import Term, const, t_add, t_eq, t_ge, t_gt, t_lt, t_mul, var
from uvil.check.shadows import evaluate_shadows
from uvil.cli import app

runner = CliRunner()

INT = ["uvil.core.int@1"]


def _spec(shadows: list[ShadowHypothesis], requires: list[Term] | None = None) -> Specification:
    return Specification(
        profile="uvil.boogie@1",
        theories=INT,
        semantics_model="model:why3-memory.v1",
        subject="p",
        contracts=Contracts(requires=requires or []),
        shadows=shadows,
    )


def test_no_shadows_is_ok() -> None:
    result = evaluate_shadows(_spec([]))
    assert result.ok
    assert not result.diagnostics
    assert not result.counterexamples


def test_refute_alignment_ok() -> None:
    # context (x >= 0) does NOT force the counter-hypothesis (x < 0).
    spec = _spec(
        [ShadowHypothesis(name="neg", formula=t_lt(var("x"), const(0)), expect="refute")],
        requires=[t_ge(var("x"), const(0))],
    )
    result = evaluate_shadows(spec)
    assert result.ok
    assert [o.status for o in result.outcomes] == ["ok"]
    assert not result.diagnostics
    assert not result.counterexamples
    (probe,) = result.probes
    assert probe.origin_backend == "shadow-probe"


def test_refute_vacuous_emits_vacuous_i7_and_counterspec_i6() -> None:
    # context (x >= 0) forces the counter-hypothesis (x >= 0) => vacuity.
    formula = t_ge(var("x"), const(0))
    spec = _spec(
        [ShadowHypothesis(name="forced", formula=formula, expect="refute")],
        requires=[t_ge(var("x"), const(0))],
    )
    result = evaluate_shadows(spec)
    assert not result.ok
    assert [o.status for o in result.outcomes] == ["vacuous"]

    (diag,) = result.diagnostics
    assert diag.kind == "vacuous"
    assert "forces the counter-hypothesis" in diag.native_message

    (cex,) = result.counterexamples
    assert cex.kind == "counterspec"
    assert cex.counter_spec == formula
    assert cex.backend_witness is not None
    assert cex.backend_witness.format == "shadow-probe"
    assert cex.shared_render.human_summary is not None
    assert cex.shared_render.human_summary.startswith("[unverified human rendering]")


def test_accept_alignment_ok() -> None:
    spec = _spec(
        [ShadowHypothesis(name="reachable", formula=t_gt(var("x"), const(0)), expect="accept")],
        requires=[t_ge(var("x"), const(0))],
    )
    result = evaluate_shadows(spec)
    assert result.ok
    assert not result.diagnostics


def test_accept_vacuous_when_spec_excludes_expected_behavior() -> None:
    spec = _spec(
        [ShadowHypothesis(name="impossible", formula=t_lt(var("x"), const(0)), expect="accept")],
        requires=[t_ge(var("x"), const(0))],
    )
    result = evaluate_shadows(spec)
    assert not result.ok
    assert [o.status for o in result.outcomes] == ["vacuous"]
    (diag,) = result.diagnostics
    assert diag.kind == "vacuous"
    assert "vacuously excludes" in diag.native_message


def test_invariants_join_the_probe_context() -> None:
    # the counter-hypothesis is forced by an invariant, not a requires clause.
    spec = Specification(
        profile="uvil.boogie@1",
        theories=INT,
        semantics_model="model:why3-memory.v1",
        subject="p",
        contracts=Contracts(invariants=[t_ge(var("x"), const(0))]),
        shadows=[
            ShadowHypothesis(name="forced", formula=t_ge(var("x"), const(0)), expect="refute")
        ],
    )
    result = evaluate_shadows(spec)
    assert [o.status for o in result.outcomes] == ["vacuous"]


def test_unknown_probe_is_never_a_pass() -> None:
    # nonlinear integer probe under a tiny budget: solver-dependent verdict,
    # but it can never be a pass (mirrors the M1 unknown test discipline).
    formula = t_eq(
        t_mul(t_mul(var("x"), var("x")), var("x")),
        t_add(t_mul(t_mul(var("y"), var("y")), var("y")), const(1)),
    )
    spec = _spec(
        [ShadowHypothesis(name="hard", formula=formula, expect="accept")],
        requires=[t_ge(var("x"), const(7)), t_ge(var("y"), const(7))],
    )
    result = evaluate_shadows(spec, timeout_ms=100)
    (outcome,) = result.outcomes
    if outcome.status in ("unknown", "timeout"):
        assert not result.ok
        (diag,) = result.diagnostics
        assert diag.kind == outcome.status
        assert "never a pass" in diag.native_message
    else:  # the pinned z3 settled it: it must have been a genuine verdict
        assert outcome.status == "ok"


def test_opaque_shadow_formula_is_a_parse_failure_not_a_pass() -> None:
    spec = _spec(
        [
            ShadowHypothesis(
                name="opaque",
                formula=Term(op="opaque", args=["FractionalPerm", "ax-1"]),
                expect="refute",
            )
        ]
    )
    result = evaluate_shadows(spec)
    assert not result.ok
    assert [o.status for o in result.outcomes] == ["parse"]
    (diag,) = result.diagnostics
    assert diag.kind == "parse"
    assert "opaque" in diag.native_message


def test_authored_fixture_spec_shadows_evaluate() -> None:
    # the authored I2 fixture carries a cap-nonneg refute shadow; requires does
    # not force it, so alignment holds.
    spec = make_spec()
    result = evaluate_shadows(spec)
    assert result.ok
    assert len(result.probes) == 1


# --- CLI: `uvil shadows` -----------------------------------------------------


def _write_spec_envelope(tmp_path: Path, spec: Specification) -> Path:
    envelope = tmp_path / "spec.json"
    envelope.write_text(
        json.dumps(
            {
                "uvil_type": spec.uvil_type,
                "schema_version": spec.schema_version,
                "artifact": spec.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    return envelope


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_cli_shadows_ok(workspace: Path) -> None:
    runner.invoke(app, ["init"])
    spec = _spec(
        [ShadowHypothesis(name="neg", formula=t_lt(var("x"), const(0)), expect="refute")],
        requires=[t_ge(var("x"), const(0))],
    )
    envelope = _write_spec_envelope(workspace, spec)
    result = runner.invoke(app, ["shadows", str(envelope)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["outcomes"][0]["status"] == "ok"
    assert payload["diagnostics"] == []


def test_cli_shadows_vacuous_records_into_cas(workspace: Path) -> None:
    from uvil.store import ContentStore

    runner.invoke(app, ["init"])
    spec = _spec(
        [ShadowHypothesis(name="forced", formula=t_ge(var("x"), const(0)), expect="refute")],
        requires=[t_ge(var("x"), const(0))],
    )
    envelope = _write_spec_envelope(workspace, spec)
    result = runner.invoke(app, ["shadows", str(envelope)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert len(payload["counterexamples"]) == 1
    assert len(payload["diagnostics"]) == 1
    store = ContentStore(workspace / ".uvil")
    for ref in (*payload["counterexamples"], *payload["diagnostics"], *payload["stored"]):
        store.get_artifact(ref)  # every recorded ref must resolve
    (cex_ref,) = payload["counterexamples"]
    cex = store.get_artifact(cex_ref)
    assert cex.kind == "counterspec"  # type: ignore[attr-defined]
    assert artifact_id(cex) == cex_ref


def test_cli_shadows_rejects_non_spec(workspace: Path) -> None:
    from tests.fixtures import make_obligation

    envelope = workspace / "not-a-spec.json"
    model = make_obligation()
    envelope.write_text(
        json.dumps(
            {
                "uvil_type": model.uvil_type,
                "schema_version": model.schema_version,
                "artifact": model.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["shadows", str(envelope)])
    assert result.exit_code == 1
