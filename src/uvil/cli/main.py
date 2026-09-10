"""`uvil` CLI entrypoint (typer).

Commands: init | put | get | render | schema | check | shadows | ledger
append/verify/diff | roots.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
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
    discipline: str = typer.Option(
        "none", "--discipline", help="Soundness discipline evidence: none or roundtrip."
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        help="Reuse cached discharged verdicts (M5 protocol); misses re-solve.",
    ),
    incremental_since: int | None = typer.Option(
        None,
        "--incremental-since",
        help="With --incremental: treat only ledger entries <= N as known.",
    ),
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
    store = ContentStore(_store_dir(state))
    ledger = _load_ledger(state)
    incremental_info: dict[str, object] | None = None
    if incremental:
        from ..protocol import check_incremental

        checked = check_incremental(
            obligations,
            store,
            ledger,
            backend=backend,
            timeout_ms=timeout_ms,
            discipline=discipline,
            incremental_since=incremental_since,
        )
        incremental_info = dict(checked.merkle)
        incremental_info["reused"] = len(checked.reused)
        incremental_info["recomputed"] = len(checked.recomputed)
        checked_result = checked.result
    else:
        checked_result = run_check(
            obligations, backend=backend, timeout_ms=timeout_ms, discipline=discipline
        )
        record(checked_result, store, ledger)

    assert checked_result.run is not None
    table = Table(title=f"verdicts ({backend})")
    table.add_column("obligation")
    table.add_column("status")
    table.add_column("ms")
    cached = set(checked_result.run.config.get("cached", []))
    for verdict in checked_result.run.verdicts:
        table.add_row(
            verdict.obligation_ref.rsplit(":", 1)[-1][:16]
            + (" (cached)" if verdict.obligation_ref in cached else ""),
            verdict.status,
            str(verdict.time_ms) if verdict.time_ms is not None else "-",
        )
    if incremental_info is not None:
        typer.echo(
            f"incremental: {incremental_info['reused']} reused / "
            f"{incremental_info['recomputed']} recomputed "
            f"(merkle {str(incremental_info['old_root'])[:16]} -> "
            f"{str(incremental_info['new_root'])[:16]})"
        )
    console.print(table)
    counts: dict[str, int] = {}
    for v in checked_result.run.verdicts:
        counts[v.status] = counts.get(v.status, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    typer.echo(f"run stored; ledger G1 appended ({summary})")


@app.command("check-lean")
def check_lean_cmd(
    files: list[Path] = typer.Argument(
        ..., exists=True, readable=True, help="Boogie files (.bpl)."
    ),
    timeout_s: float | None = typer.Option(None, "--timeout-s", help="Per-compile budget."),
    warm: bool = typer.Option(
        False, "--warm", help="Check through persistent Pantograph sessions (UVIL_PANTOGRAPH)."
    ),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Boogie input -> obligations -> Lean twin -> pinned-kernel attestation.

    Attested obligations become I5 proofs + ledger G1/G2 (kernel attestation,
    offline-replayable via `uvil attest`); failed/unsupported obligations stay
    open with I7 diagnostics - a failed proof search is never a refutation.
    Skips cleanly (exit 0) when elan is not installed; falls back to plain
    batched compiles when the warm pool is not configured.
    """
    from ..adapters.boogie.lower import import_module as boogie_import
    from ..adapters.lean.backend import PINNED_LEAN, LeanNotInstalled, LeanVersionMismatch
    from ..adapters.lean.pool import PantographNotInstalled

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

    from ..check.lean import check_lean as run_lean_check
    from ..check.lean import record_lean

    try:
        result = run_lean_check(obligations, check_timeout_s=timeout_s, warm=warm)
    except LeanNotInstalled as e:
        err.print(f"[yellow]skip[/yellow] Lean is not installed (pin: PINNED_LEAN): {e}")
        raise typer.Exit(code=0) from None
    except LeanVersionMismatch as e:
        err.print(f"[red]version mismatch[/red] {e}")
        raise typer.Exit(code=1) from e
    except PantographNotInstalled as e:
        if warm:
            err.print(f"[yellow]warm pool unavailable[/yellow] {e}; using plain compiles")
            result = run_lean_check(obligations, check_timeout_s=timeout_s, warm=False)
        else:  # pragma: no cover - only raised with warm=True
            raise

    store = ContentStore(_store_dir(state))
    record_lean(result, store, _load_ledger(state))

    assert result.run is not None
    by_obligation = {p.obligation_ref: p for p in result.proofs}
    table = Table(title=f"verdicts (lean4 {PINNED_LEAN})")
    table.add_column("obligation")
    table.add_column("status")
    table.add_column("ms")
    table.add_column("kernel")
    for verdict in result.run.verdicts:
        proof = by_obligation.get(verdict.obligation_ref)
        table.add_row(
            verdict.obligation_ref.rsplit(":", 1)[-1][:16],
            verdict.status,
            str(verdict.time_ms) if verdict.time_ms is not None else "-",
            (proof.backend.kernel_hash or "-")[:16] if proof else "-",
        )
    console.print(table)
    counts: dict[str, int] = {}
    for diag in result.diagnostics:
        counts[diag.kind] = counts.get(diag.kind, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no diagnostics"
    attested = len(result.proofs)
    typer.echo(
        f"run stored; ledger {'G1' if attested else 'G0'} appended "
        f"({attested} kernel-attested; {summary})"
    )
    for proof in result.proofs:
        typer.echo(
            f"proof: {artifact_id(proof)}  (replay offline: uvil attest {artifact_id(proof)})"
        )


@app.command("attest")
def attest(
    target: str = typer.Argument(
        ...,
        help="A stored proof artifact id, or a .lean file path to (re-)attest.",
    ),
    expect_hash: str | None = typer.Option(
        None, "--expect-hash", help="Verify the recomputed kernel hash against this value."
    ),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Offline kernel attestation replay.

    For a stored proof artifact ref: re-runs the pinned Lean kernel on the
    stored inline proof file and verifies the recorded kernel_hash. For a
    .lean file path: compiles it and prints the computed kernel hash (attach
    --expect-hash to verify). No UVIL code participates in the verification
    itself - only the pinned toolchain.
    """
    from ..adapters.lean.backend import (
        TOOLCHAIN_ID,
        LeanBackend,
        LeanNotInstalled,
        LeanVersionMismatch,
        kernel_hash,
    )
    from ..artifacts import Proof

    path = Path(target)
    inline: str
    recorded: str | None = None
    if path.exists() and path.suffix == ".lean":
        inline = path.read_text(encoding="utf-8")
        if inline.endswith("\n"):  # stored payloads carry no trailing newline
            inline = inline[:-1]
    else:
        store = ContentStore(_store_dir(state))
        try:
            model = store.get_artifact(target)
        except (KeyError, ValueError) as e:
            err.print(f"[red]error[/red] {e}")
            raise typer.Exit(code=1) from e
        if not isinstance(model, Proof):
            err.print(
                f"[red]error[/red] attest requires a proof artifact, got {type(model).__name__}"
            )
            raise typer.Exit(code=1)
        if model.payload.inline is None or model.payload.format != "lean-proof-term":
            err.print(
                f"[red]error[/red] only lean-proof-term inline payloads are replayable, "
                f"got format={model.payload.format!r}"
            )
            raise typer.Exit(code=1)
        inline = model.payload.inline
        recorded = model.backend.kernel_hash

    try:
        backend = LeanBackend()
    except LeanNotInstalled as e:
        err.print(f"[yellow]skip[/yellow] {e}")
        raise typer.Exit(code=0) from None
    except LeanVersionMismatch as e:
        err.print(f"[red]version mismatch[/red] {e}")
        raise typer.Exit(code=1) from e

    with tempfile.NamedTemporaryFile(
        "w", suffix="-attest.lean", delete=False, encoding="utf-8"
    ) as f:
        f.write(inline)
        proof_file = Path(f.name)
    try:
        proc = subprocess.run(
            [backend.executable, proof_file.name],
            capture_output=True,
            text=True,
            check=False,
            env=backend.env(),
            timeout=120,
            cwd=proof_file.parent,
        )
    finally:
        proof_file.unlink(missing_ok=True)

    computed = kernel_hash(inline)
    exit0 = proc.returncode == 0
    checks: list[tuple[str, bool]] = [("kernel exit-0", exit0)]
    expected = recorded or expect_hash
    if expected is not None:
        checks.append(("kernel hash match", computed == expected))
    table = Table(title=f"attestation replay ({TOOLCHAIN_ID})")
    table.add_column("check")
    table.add_column("result")
    for name, ok in checks:
        table.add_row(name, "[green]ok[/green]" if ok else "[red]FAILED[/red]")
    table.add_row("kernel_hash", computed)
    console.print(table)
    if not all(ok for _, ok in checks):
        err.print((proc.stdout or "") + (proc.stderr or ""))
        raise typer.Exit(code=1)
    typer.echo("attestation verified; the pinned kernel accepts this proof file offline")


@app.command("check-esbmc")
def check_esbmc_cmd(
    files: list[Path] = typer.Argument(
        ..., exists=True, readable=True, help="C harness files (.c)."
    ),
    timeout_s: float | None = typer.Option(
        None,
        "--timeout-s",
        help="Per-harness subprocess budget (--timeout is unimplemented on Windows).",
    ),
    multi_property: bool = typer.Option(
        False,
        "--multi-property",
        help=(
            "Get a verdict on every property (v8.5 has no --bug-finding; this is "
            "the documented multi-property mode)."
        ),
    ),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """C harnesses -> ESBMC (pinned binary) -> I8 run + I6 traces + ledger.

    The model-checking analogue of `uvil check`: C sources are imported into
    obligations (documented subset; out-of-subset files fail loud with I7
    parse diagnostics) and checked by the pinned ESBMC binary. Verdicts are
    run records: they never discharge or refute a deductive obligation - a
    violation carries an I6 trace, and the ledger entry is G1 (model-checking
    run record) or G0. Skips cleanly (exit 0) when ESBMC is not installed.
    """
    from ..adapters.esbmc.backend import (
        PINNED_ESBMC,
        EsbmcNotInstalled,
        EsbmcVersionMismatch,
    )
    from ..adapters.esbmc.import_c import import_c
    from ..check.esbmc import CHarness, record_esbmc
    from ..check.esbmc import check_esbmc as run_esbmc_check

    harnesses: list[CHarness] = []
    for file in files:
        source = file.read_text(encoding="utf-8")
        imported = import_c(source, filename=file.name)
        for d in imported.diagnostics:
            err.print(f"[red]I7 parse diagnostic[/red] {file}:{d.loc.line}: {d.native_message}")
        if not imported.ok:
            raise typer.Exit(code=1)
        obligations = imported.obligations
        if not obligations:
            err.print(
                f"[yellow]note[/yellow] {file}: imported with zero obligations "
                "(no assertion calls in the subset)"
            )
        harnesses.append(CHarness(source=source, filename=file.name, obligations=obligations))
    if not any(h.obligations for h in harnesses):
        err.print("[red]error[/red] no obligations found in input")
        raise typer.Exit(code=1)

    try:
        result = run_esbmc_check(harnesses, timeout_s=timeout_s, multi_property=multi_property)
    except EsbmcNotInstalled as e:
        err.print(f"[yellow]skip[/yellow] ESBMC is not installed (pin: PINNED_ESBMC): {e}")
        raise typer.Exit(code=0) from None
    except EsbmcVersionMismatch as e:
        err.print(f"[red]version mismatch[/red] {e}")
        raise typer.Exit(code=1) from e

    store = ContentStore(_store_dir(state))
    record_esbmc(result, store, _load_ledger(state))

    assert result.run is not None
    table = Table(title=f"verdicts (esbmc {PINNED_ESBMC}; model-checking run record)")
    table.add_column("obligation")
    table.add_column("status")
    table.add_column("ms")
    table.add_column("verdict")
    by_ref = {v.obligation_ref: v for v in result.run.verdicts}
    for obl in result.obligations:
        v = by_ref[artifact_id(obl)]
        table.add_row(
            v.obligation_ref.rsplit(":", 1)[-1][:16],
            v.status,
            str(v.time_ms) if v.time_ms is not None else "-",
            (v.note or "-").removeprefix("model-checking: "),
        )
    console.print(table)
    traces = len(result.counterexamples)
    counts: dict[str, int] = {}
    for diag in result.diagnostics:
        counts[diag.kind] = counts.get(diag.kind, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no diagnostics"
    typer.echo(
        f"run stored; ledger G1 appended (model-checking run record; {traces} trace(s); {summary})"
    )


@app.command("import-strata")
def import_strata_cmd(
    files: list[Path] = typer.Argument(
        ..., exists=True, readable=True, help="Strata dialect artifacts (.st)."
    ),
    out: Path | None = typer.Option(None, "--out", help="Write artifact JSONs here."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
    vendor_verify: bool = typer.Option(
        False,
        "--vendor-verify",
        help=(
            "Also run the pinned Strata-CLI (`UVIL_STRATA`) on each file and "
            "record its verdict verbatim as opaque I5 payloads "
            "(strata-verifier-result, independent=False - never a guarantee). "
            "Skipped when UVIL_STRATA is unset."
        ),
    ),
) -> None:
    """Strata dialect artifacts -> I2/I3/I4 (import only; Strata is a frontend).

    Vendor-TCB caveat: Strata unifies toward a vendor Lean core; its VC
    generation is not UVIL's TCB. Imported obligations carry guarantees only
    from UVIL's own backends (run `uvil check` on them).
    """
    from ..adapters.strata.importer import (
        STRATA_ENV_VAR,
        find_strata,
        import_strata,
        strata_verify,
        vendor_result_proof,
    )

    if vendor_verify and find_strata() is None:
        err.print(f"[yellow]skip[/yellow] {STRATA_ENV_VAR} is unset; vendor verify skipped")

    store = ContentStore(_store_dir(state)) if out is None else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    any_procedure = False
    for file in files:
        result = import_strata(file.read_text(encoding="utf-8"), filename=file.name)
        for d in result.diagnostics:
            err.print(f"[red]I7 {d.kind} diagnostic[/red] {file}:{d.loc.line}: {d.native_message}")
        if not result.procedures and result.diagnostics:
            raise typer.Exit(code=1)
        any_procedure = any_procedure or bool(result.procedures)

        verify_result = None
        if vendor_verify:
            binary = find_strata()
            if binary is not None:
                verify_result = strata_verify(binary, file)

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
            if verify_result is not None:
                for obl in proc.obligations:
                    proof = vendor_result_proof(obl, verify_result)
                    if store is not None:
                        typer.echo(store.put_artifact(proof))
                    else:
                        assert out is not None
                        payload = {
                            "uvil_type": proof.uvil_type,
                            "schema_version": proof.schema_version,
                            "artifact": proof.model_dump(mode="json"),
                        }
                        name = f"{proc.name}.proof.{len(list(out.iterdir()))}.json"
                        (out / name).write_text(
                            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
                        )
                        console.print(f"wrote {out / name}")
    if not any_procedure:
        err.print("[red]error[/red] no procedures imported")
        raise typer.Exit(code=1)


@app.command("check-isabelle")
def check_isabelle_cmd(
    files: list[Path] = typer.Argument(
        ..., exists=True, readable=True, help="Boogie files (.bpl)."
    ),
    timeout_s: float | None = typer.Option(None, "--timeout-s", help="Per-build budget."),
    state: Path = typer.Option(DEFAULT_STATE, help="State directory."),
) -> None:
    """Boogie input -> obligations -> Isabelle/HOL twin -> pinned-bundle attestation.

    The cross-language symmetric of `check-lean` (Boogie in, HOL twin out).
    Attested obligations become I5 proofs + ledger G1 (kernel attestation,
    offline-replayable via the pinned bundle); out-of-boundary obligations
    stay open with an I7 + a measured lossy I9; a failed proof search is
    never a refutation. Skips cleanly (exit 0) when Isabelle is not installed.
    """
    from ..adapters.boogie.lower import import_module as boogie_import
    from ..adapters.isabelle.backend import (
        PINNED_ISABELLE,
        IsabelleNotInstalled,
        IsabelleVersionMismatch,
    )
    from ..check.isabelle import check_isabelle as run_isabelle_check
    from ..check.isabelle import record_isabelle

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

    try:
        result = run_isabelle_check(obligations, check_timeout_s=timeout_s)
    except IsabelleNotInstalled as e:
        err.print(f"[yellow]skip[/yellow] Isabelle is not installed (pin: PINNED_ISABELLE): {e}")
        raise typer.Exit(code=0) from None
    except IsabelleVersionMismatch as e:
        err.print(f"[red]version mismatch[/red] {e}")
        raise typer.Exit(code=1) from e

    store = ContentStore(_store_dir(state))
    record_isabelle(result, store, _load_ledger(state))

    assert result.run is not None
    by_obligation = {p.obligation_ref: p for p in result.proofs}
    table = Table(title=f"verdicts (isabelle-hol {PINNED_ISABELLE})")
    table.add_column("obligation")
    table.add_column("status")
    table.add_column("ms")
    table.add_column("kernel")
    for verdict in result.run.verdicts:
        proof = by_obligation.get(verdict.obligation_ref)
        table.add_row(
            verdict.obligation_ref.rsplit(":", 1)[-1][:16],
            verdict.status,
            str(verdict.time_ms) if verdict.time_ms is not None else "-",
            (proof.backend.kernel_hash or "-")[:16] if proof else "-",
        )
    console.print(table)
    downgrades = sum(1 for t in result.translations if t.soundness_discipline == "lossy")
    attested = len(result.proofs)
    typer.echo(
        f"run stored; ledger {'G1' if attested else 'G0'} appended "
        f"({attested} HOL-attested; {downgrades} measured downgrade(s))"
    )


@app.command("bench")
def bench_cmd(
    corpus: Path = typer.Option(
        Path("corpora/churn"), "--corpus", help="Churn corpus directory (expected.json)."
    ),
    state: Path = typer.Option(
        Path(".uvil-bench"), "--state", help="Bench state directory (cache + ledger)."
    ),
    backend: str = typer.Option("z3", "--backend", help="SMT backend: z3 or cvc5."),
    json_out: bool = typer.Option(False, "--json", help="Print the metrics JSON only."),
) -> None:
    """Run the M5 churn benchmark: incremental-protocol metrics, deterministically.

    Primes the verdict cache with each committed baseline scenario, measures
    the churned run, and reports the count-based metrics (cache-hit rate,
    churn survival, control-group hit rate, partition fidelity, downgrade
    rate). Exits 1 if the recorded targets are missed.
    """
    from ..protocol.bench import results_markdown, run_benchmark, targets_met

    if not (corpus / "expected.json").exists():
        err.print(f"[red]error[/red] missing {corpus / 'expected.json'}")
        raise typer.Exit(code=1)
    result = run_benchmark(corpus, state, backend=backend)
    if json_out:
        typer.echo(json.dumps(result.metrics, sort_keys=True, indent=2))
    else:
        table = Table(title=f"churn benchmark ({backend}, {result.metrics['scenarios']} scenarios)")
        table.add_column("metric")
        table.add_column("value")
        table.add_column("target")
        rows: list[tuple[str, str, str]] = [
            ("obligations (churned runs)", str(result.metrics["obligations"]), "-"),
            ("reused", str(result.metrics["reused"]), "-"),
            ("recomputed", str(result.metrics["recomputed"]), "-"),
            (
                "cache-hit rate",
                f"{result.metrics['cache_hit_rate']:.3f}",
                f">= {result.metrics['cache_hit_target']}",
            ),
            ("no-op control hit rate", f"{result.metrics['no_op_hit_rate']:.3f}", "== 1.0"),
            (
                "churn survival",
                f"{result.metrics['churn_survival']:.3f}",
                f">= {result.metrics['churn_survival_target']}",
            ),
            ("partition fidelity", f"{result.metrics['fidelity']:.3f}", "== 1.0"),
            ("downgrade rate", f"{result.metrics['downgrade_rate']:.3f}", "== 0.0"),
        ]
        for metric, value, target in rows:
            table.add_row(metric, value, target)
        console.print(table)
        typer.echo(results_markdown(result.metrics))
    if not targets_met(result.metrics):
        err.print("[red]FAILED[/red] benchmark targets not met")
        raise typer.Exit(code=1)
    if not json_out:
        typer.echo("bench ok: targets met")


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
            for obl in proc.obligations:
                obl_id = obligation_identity(
                    spec=obl.spec_ref,
                    semantics_model=obl.semantics_model,
                    program_fragment=proc.program.fragment or proc.name,
                    profile_version=obl.target_profile.rsplit("@", 1)[-1],
                    sequent=obl.sequent,
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
