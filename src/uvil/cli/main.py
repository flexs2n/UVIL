"""`uvil` CLI entrypoint (typer).

Commands: init | put | get | render | schema | check | shadows | ledger
append/verify/diff | roots.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..adapters.boogie.lower import ImportResult, import_module
from ..artifacts import artifact_id, parse_artifact
from ..ledger import GUARANTEE_CLASSES, Attestation, Ledger
from ..schemas import build_schema
from ..store import ContentStore, merkle_root

app = typer.Typer(help="UVIL: Universal Verification Interchange Layer")
ledger_app = typer.Typer(help="Guarantee ledger operations")
app.add_typer(ledger_app, name="ledger")

console = Console()
err = Console(stderr=True)

DEFAULT_STATE = Path(".uvil")


def _store_dir(state: Path) -> Path:
    return state


def _load_ledger(state: Path) -> Ledger:
    return Ledger(state / "ledger.jsonl")


@app.command()
def init(state: Path = typer.Option(DEFAULT_STATE, help="State directory.")) -> None:
    """Initialize a UVIL workspace (object store + ledger)."""
    ContentStore(_store_dir(state))
    ledger = _load_ledger(state)
    ledger.path.touch(exist_ok=True)
    console.print(f"[green]initialized[/green] UVIL workspace at {state.resolve()}")


@app.command()
def put(
    files: list[Path] = typer.Argument(
        ..., exists=True, readable=True, help="Artifact JSON files."
    ),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Validate artifact JSON, store it, and print its artifact id."""
    store = ContentStore(_store_dir(state))
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            err.print(f"[red]parse error[/red] {file}: {e}")
            raise typer.Exit(code=1) from e
        try:
            model = parse_artifact(data)
        except Exception as e:
            err.print(f"[red]invalid artifact[/red] {file}: {e}")
            raise typer.Exit(code=1) from e
        aid = store.put_artifact(model)
        typer.echo(f"{aid}  ({file})")


@app.command()
def get(
    artifact_id_str: str = typer.Argument(..., help="Artifact id (uvil:<type>@<version>:<hash>)."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Fetch an artifact from the store and print its canonical JSON."""
    store = ContentStore(_store_dir(state))
    try:
        model = store.get_artifact(artifact_id_str)
    except (KeyError, ValueError) as e:
        err.print(f"[red]error[/red] {e}")
        raise typer.Exit(code=1) from e
    typer.echo(json.dumps(model.model_dump(mode="json"), sort_keys=True))


@app.command()
def render(
    target: str = typer.Argument(
        ..., help="Artifact id (uvil:<type>@<version>:<hash>) or path to an envelope JSON file."
    ),
    form: str = typer.Option("json", "--form", help="Output form: json (common-JSON) or human."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Render an I6/I7 artifact as common JSON (machine) or human text."""
    from ..artifacts import Counterexample, Diagnostic

    path = Path(target)
    model: object
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            model = parse_artifact(data)
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
            err.print(f"[red]error[/red] cannot load artifact from {path}: {e}")
            raise typer.Exit(code=1) from e
    else:
        store = ContentStore(_store_dir(state))
        try:
            model = store.get_artifact(target)
        except (KeyError, ValueError) as e:
            err.print(f"[red]error[/red] {e}")
            raise typer.Exit(code=1) from e
    if not isinstance(model, (Counterexample, Diagnostic)):
        err.print(
            f"[red]error[/red] render supports I6 counterexample / I7 diagnostic only, "
            f"got {type(model).__name__}"
        )
        raise typer.Exit(code=1)

    from ..render import to_common_json, to_human

    if form == "json":
        typer.echo(json.dumps(to_common_json(model), sort_keys=True))
    elif form == "human":
        typer.echo(to_human(model))
    else:
        err.print(f"[red]error[/red] unknown form {form!r} (expected 'json' or 'human')")
        raise typer.Exit(code=1)


@app.command("schema")
def schema(
    uvil_type: str | None = typer.Argument(None, help="Artifact type (e.g. obligation)."),
    all_schemas: bool = typer.Option(False, "--all", help="Export every type."),
    out: Path | None = typer.Option(None, "--out", help="Directory to write into."),
) -> None:
    """Print or export the JSON Schema for artifact types."""
    if all_schemas:
        if out is None:
            err.print("[red]--all requires --out DIR[/red]")
            raise typer.Exit(code=1)
        from ..schemas import export_schemas

        for path in export_schemas(out):
            console.print(f"wrote {path}")
        return
    if uvil_type is None:
        err.print("provide a type or --all")
        raise typer.Exit(code=1)
    try:
        payload = build_schema(uvil_type)
    except ValueError as e:
        err.print(f"[red]error[/red] {e}")
        raise typer.Exit(code=1) from e
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / f"uvil.{uvil_type}.schema.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        console.print(f"wrote {out / f'uvil.{uvil_type}.schema.json'}")
    else:
        typer.echo(json.dumps(payload, sort_keys=True))


@app.command()
def roots(
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Merkle root over all artifacts currently in the store."""
    store = ContentStore(_store_dir(state))
    digests = [p.name for d in store.objects.iterdir() if d.is_dir() for p in d.iterdir()]
    table = Table(title="store summary")
    table.add_column("objects")
    table.add_column("merkle root")
    table.add_row(str(len(digests)), merkle_root(digests) if digests else "-")
    console.print(table)


@app.command()
def translate(
    file: Path = typer.Argument(..., exists=True, readable=True, help="Dafny source (.dfy)."),
    out: Path | None = typer.Option(None, "--out", help="Write artifact JSONs here."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Dafny -> Boogie text (pinned wrapper) -> I2/I4 artifacts.

    Skips with a clear message (exit 0) when Dafny is not installed; hard-fails
    on a version mismatch with PINNED_DAFNY (ADR 0002).
    """
    from ..adapters.boogie.dafny import DafnyFrontend, DafnyNotInstalled, DafnyVersionMismatch

    frontend = DafnyFrontend()
    try:
        boogie_text = frontend.translate(file)
    except DafnyNotInstalled:
        err.print("[yellow]skip[/yellow] Dafny is not installed (pin: PINNED_DAFNY)")
        raise typer.Exit(code=0) from None
    except DafnyVersionMismatch as e:
        err.print(f"[red]version mismatch[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        err.print(f"[red]translate failed[/red] {e}")
        raise typer.Exit(code=1) from e

    result = import_module(boogie_text, filename=file.name)
    _emit_import(result, out, state)


def _emit_import(result: ImportResult, out: Path | None, state: Path) -> None:
    for d in result.diagnostics:
        err.print(f"[red]I7 parse diagnostic[/red] {d.loc.file}:{d.loc.line}: {d.native_message}")
    if not result.procedures and result.diagnostics:
        raise typer.Exit(code=1)
    store = ContentStore(_store_dir(state)) if out is None else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    for proc in result.procedures.values():
        for model in (proc.program, proc.spec, *proc.obligations):
            if store is not None:
                typer.echo(store.put_artifact(model))
            else:
                assert out is not None
                payload = {
                    "uvil_type": model.uvil_type,
                    "schema_version": model.schema_version,
                    "artifact": model.model_dump(mode="json"),
                }
                name = f"{proc.name}.{model.uvil_type}.{len(list(out.iterdir()))}.json"
                text = json.dumps(payload, indent=2, sort_keys=True)
                (out / name).write_text(text, encoding="utf-8")
                console.print(f"wrote {out / name}")


@app.command()
def check(
    files: list[Path] = typer.Argument(
        ..., exists=True, readable=True, help="Boogie files (.bpl)."
    ),
    backend: str = typer.Option("z3", "--backend", help="SMT backend: z3 or cvc5."),
    timeout_s: float | None = typer.Option(None, "--timeout-s", help="Per-obligation budget."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Boogie input -> obligations -> SMT check -> verdict table + ledger G1."""
    from ..adapters.boogie.lower import import_module as boogie_import

    obligations = []
    for file in files:
        imported = boogie_import(file.read_text(encoding="utf-8"), filename=file.name)
        for d in imported.diagnostics:
            err.print(f"[red]I7 parse diagnostic[/red] {file}:{d.loc.line}: {d.native_message}")
        if not imported.ok:
            raise typer.Exit(code=1)
        obligations.extend(imported.obligations)
    if not obligations:
        err.print("[red]error[/red] no obligations found in input")
        raise typer.Exit(code=1)

    from ..check.core import check as run_check
    from ..check.core import record

    timeout_ms = int(timeout_s * 1000) if timeout_s is not None else None
    checked = run_check(obligations, backend=backend, timeout_ms=timeout_ms)
    record(checked, ContentStore(_store_dir(state)), _load_ledger(state))

    assert checked.run is not None
    table = Table(title=f"verdicts ({backend})")
    table.add_column("obligation")
    table.add_column("status")
    table.add_column("ms")
    for verdict in checked.run.verdicts:
        table.add_row(
            verdict.obligation_ref.rsplit(":", 1)[-1][:16],
            verdict.status,
            str(verdict.time_ms) if verdict.time_ms is not None else "-",
        )
    console.print(table)
    counts: dict[str, int] = {}
    for v in checked.run.verdicts:
        counts[v.status] = counts.get(v.status, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    typer.echo(f"run stored; ledger G1 appended ({summary})")


@app.command()
def shadows(
    spec_file: Path = typer.Argument(
        ..., exists=True, readable=True, help="Specification artifact envelope JSON."
    ),
    backend: str = typer.Option("z3", "--backend", help="SMT backend: z3 or cvc5."),
    timeout_s: float | None = typer.Option(None, "--timeout-s", help="Per-probe budget."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory; records I6/I7 into the CAS."),
) -> None:
    """Evaluate a spec's shadow set (R4): vacuity probes per shadow hypothesis."""
    import dataclasses

    from ..artifacts import Specification

    try:
        data = json.loads(spec_file.read_text(encoding="utf-8"))
        model = parse_artifact(data, expected_type="specification")
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        err.print(f"[red]error[/red] cannot load specification from {spec_file}: {e}")
        raise typer.Exit(code=1) from e
    assert isinstance(model, Specification)

    from ..check.shadows import evaluate_shadows

    timeout_ms = int(timeout_s * 1000) if timeout_s is not None else None
    result = evaluate_shadows(model, backend=backend, timeout_ms=timeout_ms)

    table = Table(title=f"shadow set ({backend})")
    table.add_column("shadow")
    table.add_column("expect")
    table.add_column("status")
    table.add_column("detail")
    for outcome in result.outcomes:
        table.add_row(outcome.name, outcome.expect, outcome.status, outcome.detail)
    console.print(table)

    store = ContentStore(_store_dir(state))
    stored = [store.put_artifact(a) for a in (*result.counterexamples, *result.diagnostics)]
    typer.echo(
        json.dumps(
            {
                "ok": result.ok,
                "outcomes": [dataclasses.asdict(o) for o in result.outcomes],
                "counterexamples": [artifact_id(a) for a in result.counterexamples],
                "diagnostics": [artifact_id(a) for a in result.diagnostics],
                "stored": stored,
            },
            sort_keys=True,
        )
    )


corpus_app = typer.Typer(help="Corpus operations")
app.add_typer(corpus_app, name="corpus")


@corpus_app.command("verify")
def corpus_verify(
    corpus_dir: Path = typer.Argument(
        Path("corpora/boogie"), exists=True, help="Corpus directory with expected.json."
    ),
) -> None:
    """Recompute obligation identities for every corpus entry and check them
    against expected.json (no solving)."""
    expected_path = corpus_dir / "expected.json"
    if not expected_path.exists():
        err.print(f"[red]error[/red] missing {expected_path}")
        raise typer.Exit(code=1)
    expected: dict[str, dict[str, str]] = json.loads(expected_path.read_text(encoding="utf-8"))[
        "expected"
    ]

    from ..adapters.boogie.lower import import_module as boogie_import
    from ..store import obligation_identity

    problems = 0
    seen: set[str] = set()
    for rel_path in sorted({e["file"] for e in expected.values()}):
        path = corpus_dir / rel_path
        if not path.exists():
            err.print(f"[red]missing corpus file[/red] {path}")
            problems += 1
            continue
        result = boogie_import(path.read_text(encoding="utf-8"), filename=path.name)
        if not result.ok:
            for d in result.diagnostics:
                err.print(f"[red]I7 parse diagnostic[/red] {path}:{d.loc.line}: {d.native_message}")
            problems += 1
            continue
        for proc in result.procedures.values():
            (obl,) = proc.obligations
            obl_id = obligation_identity(
                spec=obl.spec_ref,
                semantics_model=obl.semantics_model,
                program_fragment=proc.program.fragment or proc.name,
                profile_version=obl.target_profile.rsplit("@", 1)[-1],
            )
            seen.add(obl_id)
            if obl_id not in expected:
                err.print(f"[red]unknown identity[/red] {path}/{proc.name}")
                problems += 1
    for obl_id in expected:
        if obl_id not in seen:
            err.print(f"[red]stale manifest entry[/red] {obl_id}")
            problems += 1
    if problems:
        failed = f"{problems} problem(s), {len(seen)}/{len(expected)} identities verified"
        err.print(f"[red]FAILED[/red] {failed}")
        raise typer.Exit(code=1)
    console.print(f"[green]ok[/green] {len(seen)} identities match expected.json")


@ledger_app.command("append")
def ledger_append(
    refs: list[str] = typer.Option(..., "--ref", help="Artifact reference (repeatable)."),
    guarantee: str = typer.Option(..., "--guarantee", help=f"One of {GUARANTEE_CLASSES}."),
    tool: str | None = typer.Option(None, "--tool", help="Attesting tool name."),
    version: str | None = typer.Option(None, "--version", help="Attesting tool version."),
    kernel_hash: str | None = typer.Option(None, "--kernel-hash", help="Kernel hash."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Append a guarantee entry to the ledger."""
    ledger = _load_ledger(state)
    attestation = (
        Attestation(tool=tool or "unknown", version=version, kernel_hash=kernel_hash)
        if (tool or kernel_hash)
        else None
    )
    try:
        entry = ledger.append(refs, guarantee, attestation=attestation)
    except ValueError as e:
        err.print(f"[red]error[/red] {e}")
        raise typer.Exit(code=1) from e
    console.print(f"appended seq={entry.seq} {entry.guarantee_class} {entry.entry_hash}")


@ledger_app.command("verify")
def ledger_verify(state: Path = typer.Option(DEFAULT_STATE, help="State directory.")) -> None:
    """Verify the ledger hash chain (tamper evidence)."""
    ledger = _load_ledger(state)
    defects = ledger.verify()
    if defects:
        for d in defects:
            err.print(f"[red]DEFECT[/red] {d}")
        raise typer.Exit(code=1)
    count = len(ledger.entries())
    console.print(f"[green]ok[/green] ledger intact ({count} entries, chain verified)")


@ledger_app.command("diff")
def ledger_diff(
    other: Path = typer.Argument(..., exists=True, help="Another ledger.jsonl to diff against."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Diff two ledger journals by entry hash."""
    ledger = _load_ledger(state)
    result = ledger.diff(Ledger(other))
    console.print_json(json.dumps(result, sort_keys=True))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
