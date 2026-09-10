"""Churn benchmark tests: corpus discipline, identity partitions, thresholds.

The committed corpus is the exit criterion: manifest and disk agree, the
generator is deterministic (byte-identical rebuild), and a full benchmark run
over the committed corpus reproduces the committed metrics deterministically
(count-based metrics, no wall-clock) and meets the recorded targets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from gen_churn import CYCLE, PROCS_PER_SCENARIO, build_churn_scenarios  # noqa: E402

from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.protocol.bench import (  # noqa: E402
    CONTROL_FAMILY,
    run_benchmark,
    targets_met,
)

CORPUS = REPO_ROOT / "corpora" / "churn"
MANIFEST = json.loads((CORPUS / "expected.json").read_text(encoding="utf-8"))
SCENARIOS: dict[str, dict] = MANIFEST["scenarios"]


def test_manifest_and_disk_equal() -> None:
    listed = {e["file"] for e in SCENARIOS.values()}
    on_disk = {p.relative_to(CORPUS).as_posix() for p in CORPUS.rglob("*.bpl")}
    assert listed == on_disk, "manifest and disk disagree (posix paths required)"


def test_corpus_shape() -> None:
    assert len(SCENARIOS) >= 60
    families = {e["family"] for e in SCENARIOS.values()}
    assert families == {"no-op-reorder", "spec-churn", "code-churn", "library-churn"}
    counts: dict[str, int] = {}
    for e in SCENARIOS.values():
        counts[e["family"]] = counts.get(e["family"], 0) + 1
    assert counts["no-op-reorder"] == 30
    assert counts["spec-churn"] == 10
    assert counts["code-churn"] == 10
    assert counts["library-churn"] == 10
    assert set(CYCLE) == families


def test_baseline_scenarios_are_wellformed() -> None:
    for name, entry in sorted(SCENARIOS.items()):
        imported = import_module((CORPUS / entry["file"]).read_text(encoding="utf-8"), name)
        assert imported.ok, name
        assert len(imported.procedures) == PROCS_PER_SCENARIO, name
        for proc in imported.procedures.values():
            assert len(proc.obligations) == 1, name  # corpus discipline


def test_generator_is_deterministic_and_matches_disk() -> None:
    a = build_churn_scenarios()
    b = build_churn_scenarios()
    assert [(n, f, s, m) for n, f, s, m, _ in a] == [(n, f, s, m) for n, f, s, m, _ in b]
    for name, _family, source, _mutate, _procs in a:
        path = CORPUS / "scenarios" / f"{name}.bpl"
        assert path.exists(), name
        assert path.read_text(encoding="utf-8") == source, name


def test_expected_partitions_per_family() -> None:
    for name, entry in SCENARIOS.items():
        procs = {f"p{j}" for j in range(PROCS_PER_SCENARIO)}
        expected = entry["expected"]
        assert set(expected) == procs, name
        assert set(expected.values()) <= {"reused", "recomputed"}, name
        if entry["family"] == CONTROL_FAMILY:
            assert set(expected.values()) == {"reused"}, name
        elif entry["family"] == "library-churn":
            assert set(expected.values()) == {"recomputed"}, name
        else:  # partial mutation: exactly one recomputed
            recomputed = {p for p, v in expected.items() if v == "recomputed"}
            assert recomputed == set(entry["mutate"]), name


def test_benchmark_meets_targets_deterministically(tmp_path: Path) -> None:
    result = run_benchmark(CORPUS, tmp_path, backend="z3")
    metrics = result.metrics
    assert metrics["scenarios"] == len(SCENARIOS)
    # the committed RESULTS.md numbers reproduce
    committed = (CORPUS / "RESULTS.md").read_text(encoding="utf-8")
    assert f"| cache-hit rate | {metrics['cache_hit_rate']:.3f} |" in committed
    assert f"| churn survival | {metrics['churn_survival']:.3f} |" in committed
    assert f"| partition fidelity | {metrics['fidelity']:.3f} |" in committed
    assert f"| downgrade rate | {metrics['downgrade_rate']:.3f} |" in committed
    # recorded targets
    assert metrics["cache_hit_rate"] >= 0.70
    assert metrics["churn_survival"] >= 0.30
    assert metrics["no_op_hit_rate"] == 1.0
    assert metrics["fidelity"] == 1.0
    assert metrics["downgrade_rate"] == 0.0
    assert targets_met(metrics)


def test_no_op_reorder_control_is_fully_reused(tmp_path: Path) -> None:
    result = run_benchmark(CORPUS, tmp_path, backend="z3")
    control = [o for o in result.outcomes if o.family == CONTROL_FAMILY]
    assert control
    for outcome in control:
        assert outcome.recomputed == []
        assert len(outcome.reused) == PROCS_PER_SCENARIO


def test_library_churn_recomputes_everything(tmp_path: Path) -> None:
    result = run_benchmark(CORPUS, tmp_path, backend="z3")
    library = [o for o in result.outcomes if o.family == "library-churn"]
    assert library
    for outcome in library:
        assert outcome.reused == []
        assert len(outcome.recomputed) == PROCS_PER_SCENARIO


def test_partial_churn_preserves_untouched_obligations(tmp_path: Path) -> None:
    result = run_benchmark(CORPUS, tmp_path, backend="z3")
    for outcome in result.outcomes:
        if outcome.family in ("spec-churn", "code-churn"):
            assert set(outcome.reused) == {f"p{j}" for j in range(PROCS_PER_SCENARIO)} - set(
                outcome.recomputed
            )
            assert len(outcome.recomputed) == 1


def test_bench_cli_reproducible(tmp_path: Path) -> None:
    from uvil.cli import app

    # mini corpus: first cycle of the committed builder (6 scenarios)
    mini = tmp_path / "churn"
    (mini / "scenarios").mkdir(parents=True)
    scenarios = build_churn_scenarios()[: len(CYCLE)]
    manifest = {
        "meta": {"seed": 0, "z3_pin": "5.1.0", "corpus_version": 1},
        "scenarios": {
            name: {
                "file": f"scenarios/{name}.bpl",
                "family": family,
                "mutate": list(mutate),
                "expected": {
                    f"p{j}": (
                        "reused"
                        if family == CONTROL_FAMILY
                        or (family in ("spec-churn", "code-churn") and f"p{j}" not in mutate)
                        else "recomputed"
                    )
                    for j in range(PROCS_PER_SCENARIO)
                },
                "expected_status": "discharged",
            }
            for name, family, source, mutate, _procs in scenarios
        },
    }
    (mini / "expected.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    for name, _family, source, _mutate, _procs in scenarios:
        (mini / "scenarios" / f"{name}.bpl").write_text(source, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app, ["bench", "--corpus", str(mini), "--state", str(tmp_path / "state"), "--json"]
    )
    assert result.exit_code == 0, result.output
    metrics = json.loads(result.output)
    assert metrics["cache_hit_rate"] >= 0.70
    assert targets_met(metrics)

    # a fresh state reproduces the identical metrics (count-based determinism;
    # a warm state legitimately hits everything - the cache doing its job)
    result = runner.invoke(
        app, ["bench", "--corpus", str(mini), "--state", str(tmp_path / "state2"), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == metrics


def test_bench_cli_missing_corpus_fails(tmp_path: Path) -> None:
    from uvil.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["bench", "--corpus", str(tmp_path / "nope"), "--state", str(tmp_path / "s")]
    )
    assert result.exit_code == 1
