from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.fixtures import make_obligation
from uvil.artifacts import artifact_id, canonical_bytes
from uvil.cli import app

runner = CliRunner()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_artifact(tmp: Path) -> tuple[Path, str]:
    model = make_obligation()
    path = tmp / "obligation.json"
    path.write_text(
        json.dumps(
            {
                "uvil_type": model.uvil_type,
                "schema_version": model.schema_version,
                "artifact": model.model_dump(mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path, artifact_id(model)


def test_init_put_get_flow(workspace: Path) -> None:
    assert runner.invoke(app, ["init"]).exit_code == 0
    path, aid = write_artifact(workspace)
    result = runner.invoke(app, ["put", str(path)])
    assert result.exit_code == 0, result.output
    assert aid in result.output

    result = runner.invoke(app, ["get", aid])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == json.loads(canonical_bytes(make_obligation()).decode())


def test_put_rejects_invalid_artifact(workspace: Path) -> None:
    runner.invoke(app, ["init"])
    bad = workspace / "bad.json"
    bad.write_text('{"uvil_type": "obligation", "artifact": {"nonsense": true}}', encoding="utf-8")
    result = runner.invoke(app, ["put", str(bad)])
    assert result.exit_code == 1


def test_schema_single(workspace: Path) -> None:
    result = runner.invoke(app, ["schema", "obligation"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["title"] == "uvil.obligation@1"


def test_schema_all_export(workspace: Path) -> None:
    out = workspace / "schemas"
    result = runner.invoke(app, ["schema", "--all", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert len(list(out.glob("uvil.*.schema.json"))) == 9


def test_ledger_flow(workspace: Path) -> None:
    runner.invoke(app, ["init"])
    _, aid = write_artifact(workspace)
    result = runner.invoke(
        app,
        [
            "ledger",
            "append",
            "--ref",
            aid,
            "--guarantee",
            "G1",
            "--tool",
            "z3",
            "--version",
            "4.13.0",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["ledger", "verify"])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output

    other = workspace / "other.jsonl"
    other.touch()
    result = runner.invoke(app, ["ledger", "diff", str(other)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["only_in_self"]) == 1


def test_ledger_verify_fails_on_tamper(workspace: Path) -> None:
    runner.invoke(app, ["init"])
    _, aid = write_artifact(workspace)
    runner.invoke(app, ["ledger", "append", "--ref", aid, "--guarantee", "G0"])
    ledger_path = workspace / ".uvil" / "ledger.jsonl"
    record = json.loads(ledger_path.read_text(encoding="utf-8"))
    record["guarantee_class"] = "G4"
    ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["ledger", "verify"])
    assert result.exit_code == 1
