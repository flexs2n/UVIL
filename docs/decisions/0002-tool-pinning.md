# ADR 0002: Tool pinning — exact solver and frontend versions are correctness

- Status: accepted
- Date: 2026-09-08
- Deciders: UVIL maintainers

## Context

M1 lands real solver and frontend integrations: in-process z3 (pip wheel), a
Dafny wrapper (`dafny translate boogie`), and an optional cvc5 subprocess backend.
Backend VC extraction and SMT verdicts are brittle across tool versions: a
"discharged" recorded against z3 4.13 may not replay against z3 5.x, and Dafny's
Boogie emission format drifts between releases. ADR 0001 already requires golden
tests per pinned tool version; this ADR fixes *which* versions and what happens
on mismatch.

## Decision

1. **z3-solver is hard-pinned** to `==5.1.0.0` in `pyproject.toml` (`smt`/`dev`
   extras). `Z3Backend` refuses to construct against any other installed version.
   Corpus `expected.json` verdicts are recorded with this version; corpus tests
   verify them with it.
2. **Dafny is pinned via the `PINNED_DAFNY` constant** (currently `"4.9.0"`),
   recorded at install time:
   `dotnet tool install --global Dafny --version 4.9.0`.
   - Version discovery runs `dafny --version` on every translate; the first
     `major.minor.patch` triple must equal the pin.
   - A present-but-different Dafny is a **hard failure** (I7 `semantic-mismatch`
     upstream) — never a downgrade to a warning.
   - A completely absent Dafny raises `DafnyNotInstalled`: CLI paths skip
     cleanly (exit 0), tests skip (`skipif`), demos document the skip.
3. **cvc5 is optional**: no pip wheel exists for Windows, so it is a subprocess
   backend enabled only when `UVIL_CVC5` points at a pinned binary. Its exact
   version is recorded in the I8 Run attestation whenever it is used. Golden
   tests for cvc5 skip when the binary is absent and fail when a
   present-but-unpinned binary reports an unparseable version.
4. **Golden snapshots carry provenance**: corpus metadata names the z3 pin and
   the budgets used at generation time. Tests fail on a present-but-mismatched
   binary and skip only when the binary is entirely absent.
5. Solver verdicts are recorded as **solver-verdict G1** ledger entries: the
   attestation carries tool name, exact version, and a hash committing to the
   I8 Run. No certificates are attached yet — the Alethe/LFSC certificate-
   checking upgrade path is M4+ and will tighten G1 to certificate-checked.

## Consequences

- Upgrading z3/Dafny/cvc5 is a deliberate, reviewable change: bump the pin,
  regenerate corpus verdicts, regenerate golden snapshots, and record the new
  version here.
- CI environments must install the pinned z3 wheel (`pip install -e ".[dev]"`
  suffices) and may omit Dafny/cvc5 (dependent tests self-skip).
- Version drift between generation-time and verification-time tools surfaces as
  explicit test failures, not silent guarantee drift.
