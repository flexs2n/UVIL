"""Renderer golden tests: common-JSON + human renders for every I6 shape and I7 kind.

This is the M2 exit-criterion gate ("renderer golden tests green"): the common
JSON is the single machine interface repair agents consume, so its exact shape
is pinned per I6 kind (valuation/trace/scenario/counterspec) and per I7 kind.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import get_args

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures import (
    make_counterexample,
    make_counterspec_counterexample,
    make_diagnostic_of_kind,
    make_scenario_counterexample,
    make_trace_counterexample,
)
from uvil.artifacts import Counterexample
from uvil.artifacts.counterexample import BackendWitness
from uvil.artifacts.diagnostic import DiagnosticKind
from uvil.render import to_backend_render, to_common_json, to_human

I6_MAKERS: dict[str, Callable[[], Counterexample]] = {
    "valuation": lambda: make_counterexample("obl:x"),
    "trace": lambda: make_trace_counterexample("obl:x"),
    "scenario": lambda: make_scenario_counterexample("obl:x"),
    "counterspec": lambda: make_counterspec_counterexample("obl:x"),
}
I7_KINDS = get_args(DiagnosticKind)


def test_all_four_i6_shapes_and_six_i7_kinds_covered() -> None:
    assert set(I6_MAKERS) == {"valuation", "trace", "scenario", "counterspec"}
    assert set(I7_KINDS) == {
        "unproved",
        "vacuous",
        "timeout",
        "parse",
        "semantic-mismatch",
        "unknown",
    }


@pytest.mark.parametrize("maker", I6_MAKERS.values(), ids=I6_MAKERS)
class TestI6Goldens:
    def test_common_json(
        self, maker: Callable[[], Counterexample], snapshot: SnapshotAssertion
    ) -> None:
        assert to_common_json(maker()) == snapshot

    def test_human(self, maker: Callable[[], Counterexample], snapshot: SnapshotAssertion) -> None:
        assert to_human(maker()) == snapshot


@pytest.mark.parametrize("kind", I7_KINDS)
class TestI7Goldens:
    def test_common_json(self, kind: str, snapshot: SnapshotAssertion) -> None:
        assert to_common_json(make_diagnostic_of_kind(kind)) == snapshot  # type: ignore[arg-type]

    def test_human(self, kind: str, snapshot: SnapshotAssertion) -> None:
        assert to_human(make_diagnostic_of_kind(kind)) == snapshot  # type: ignore[arg-type]


@pytest.mark.parametrize("maker", I6_MAKERS.values(), ids=I6_MAKERS)
def test_common_json_is_stable_sorted(maker: Callable[[], Counterexample]) -> None:
    payload = to_common_json(maker())
    once = json.dumps(payload, sort_keys=True)
    reparsed = json.loads(once)
    again = json.dumps(reparsed, sort_keys=True)
    assert once == again


def test_human_always_prefixed() -> None:
    for maker in I6_MAKERS.values():
        assert to_human(maker()).startswith("[unverified human rendering]")
    for kind in I7_KINDS:
        assert to_human(make_diagnostic_of_kind(kind)).startswith("[unverified human rendering]")  # type: ignore[arg-type]


def test_smt_backend_render_is_verbatim_model_text() -> None:
    model_text = "((len 3) (cap 2))"
    cex = make_counterexample("obl:x").model_copy(
        update={"backend_witness": BackendWitness(format="smt-lib2-model", payload=model_text)}
    )
    assert to_backend_render(cex) == model_text


def test_backend_render_dispatches_traces_to_esbmc_m4() -> None:
    # M4: the ESBMC adapter produces kind="trace" I6s; their backend render
    # is the verbatim report text (dispatch lives in uvil.render)
    from uvil.adapters.esbmc.cex import ESBMC_TRACE_FORMAT

    report = '[{"status": "violation", "steps": []}]'
    cex = make_trace_counterexample("obl:x").model_copy(
        update={
            "trace": [],
            "backend_witness": BackendWitness(format=ESBMC_TRACE_FORMAT, payload=report),
        }
    )
    assert to_backend_render(cex) == report


def test_backend_render_fails_loudly_without_backend_producer() -> None:
    # scenario has no producer until a TLC adapter exists (M4 leaves it loud)
    for name in ("scenario", "counterspec"):
        cex = I6_MAKERS[name]()
        with pytest.raises(NotImplementedError, match="no backend render"):
            to_backend_render(cex)


def test_smt_backend_render_fails_loudly_without_witness() -> None:
    cex = make_counterexample("obl:x").model_copy(update={"backend_witness": None})
    with pytest.raises(NotImplementedError, match="witness format=None"):
        to_backend_render(cex)


def test_common_json_rejects_non_i6_i7() -> None:
    from tests.fixtures import make_obligation

    with pytest.raises(TypeError, match="I6/I7"):
        to_common_json(make_obligation())  # type: ignore[arg-type]


def test_i7_diagnostic_fixture_builder_covers_all_kinds() -> None:
    for kind in I7_KINDS:
        diag = make_diagnostic_of_kind(kind)  # type: ignore[arg-type]
        assert diag.kind == kind
        assert diag.native_message


# --- CLI: `uvil render` ------------------------------------------------------

from typer.testing import CliRunner  # noqa: E402

from uvil.artifacts import artifact_id  # noqa: E402
from uvil.cli import app  # noqa: E402

runner = CliRunner()


def _write_envelope(tmp_path, model) -> Path:
    envelope = tmp_path / "artifact.json"
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
    return envelope


def test_cli_render_from_file_json_and_human(tmp_path) -> None:
    envelope = _write_envelope(tmp_path, make_trace_counterexample("obl:x"))
    result = runner.invoke(app, ["render", str(envelope)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["kind"] == "trace"
    assert payload["backend_witness"] == {"format": "esbmc-trace"}

    result = runner.invoke(app, ["render", str(envelope), "--form", "human"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("[unverified human rendering]")


def test_cli_render_from_store(tmp_path, monkeypatch) -> None:
    from uvil.store import ContentStore

    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    cex = make_counterexample("obl:x")
    ContentStore(tmp_path / ".uvil").put_artifact(cex)
    result = runner.invoke(app, ["render", artifact_id(cex)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["kind"] == "valuation"


def test_cli_render_rejects_non_i6_i7_and_bad_form(tmp_path) -> None:
    from tests.fixtures import make_obligation

    envelope = _write_envelope(tmp_path, make_obligation())
    result = runner.invoke(app, ["render", str(envelope)])
    assert result.exit_code == 1
    assert "I6" in result.output

    good = _write_envelope(tmp_path, make_counterexample("obl:x"))
    result = runner.invoke(app, ["render", str(good), "--form", "s-expression"])
    assert result.exit_code == 1
    assert "form" in result.output
