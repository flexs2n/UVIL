# UVIL: Universal Verification Interchange Layer

UVIL is a neutral artifact format and adapter architecture for software
verification tools. It is a Python reference implementation, not a verifier.

## About

**The problem.** Verification artifacts do not travel between tools. A
specification, verification condition, proof term, counterexample, failure
diagnostic, or verification run produced inside one tool (Dafny, Lean 4,
Isabelle/HOL, ESBMC, a solver like z3) is encoded in that tool's own format
and cannot be consumed by another tool's pipeline without bespoke, hand-built
translation code. Recent agent systems that orchestrate verification are each
coupled to a single backend this way (surveyed in the design draft [5]), and
the cross-prover benchmark ITPEval
measures that ecosystem-tier proof translation between interactive theorem
provers succeeds at 5.2% pass@1, against 29.7% for controlled axiomatized
theorems [1]. The fragmentation is a data-format problem as much as a logic
problem: there is no shared, versioned, content-addressed format for the
artifacts themselves.

**What UVIL does about it.** UVIL standardizes the artifacts rather than the
logics. It defines nine artifact types (intent, specification, program,
obligation, proof or certificate, counterexample, failure diagnostic,
verification run, translation), each serialized canonically, content-addressed
by hash, and exported as a versioned JSON Schema. The shared assertion
language is a subset of the SMT-LIB v2 core theories [4], and a
semantics-model registry records which program semantics an artifact is
phrased over, the piece that turns implicit library context into hashable,
citable metadata (the Why3 separation of VC generation from provers [3],
generalized into a registry). Adapters move artifacts
between the shared format and concrete tools, and every boundary crossing
records which soundness discipline applied. The design goals are:

1. **Fail loud on semantic loss.** A translation that cannot discharge its
   soundness obligation emits a `lossy` marker with residual obligations. It
   never silently weakens a specification. Spec weakening is a hard error.
2. **No trusted middle layer.** UVIL never re-verifies a kernel's work and
   never upgrades an `unknown` or `timeout` verdict. A `discharged` obligation
   references a proof whose kernel attestation can be replayed offline with
   the pinned toolchain alone.
3. **Provenance.** An append-only, hash-chained guarantee ledger records, for
   every verdict, the tool, its version, and what class of guarantee (G0 to
   G4) it carries. The journal is tamper-evident and machine-diffable.
4. **Incremental checking.** Verdicts are cached under an obligation identity
   (a hash over spec, semantics model, program fragment, and profile version,
   pinned to the backend and tool version). Changed obligation sets are
   summarized by a Merkle diff, so re-verification after spec, code, or
   library churn re-solves only what changed.

The full design specification, including the artifact schemas and the
soundness rules (R1 to R4), is `draft.md` (sections 5 and 6) in the project
root; architecture decisions are recorded in `docs/decisions/` (ADRs 0001 to
0007). This kind of verified-infrastructure work has precedent at the
compiler level, e.g. Vellvm, a formalization of LLVM IR in a proof assistant
[2]; UVIL applies an interchange-layer approach to program-verification
artifacts across heterogeneous backends instead.

## Prerequisites

- **Python >= 3.12** and `pip`. This is the only hard requirement; the SMT
  backend (z3 5.1.0) installs as a pip wheel with the extras.

All other backends are optional and skip-if-absent: the tests and CLI paths
that need them skip cleanly when the tool is missing.

| Tool | Used for | Pin | Enable via |
|---|---|---|---|
| z3-solver | SMT checking (primary backend) | `5.1.0.0` pip wheel | automatic |
| elan / Lean 4 | kernel-attested Lean twins | toolchain `leanprover/lean4:v4.33.1` | on PATH or `~/.elan/bin` |
| Dafny | Dafny to Boogie import wrapper | `4.9.0` (dotnet tool) | on PATH |
| cvc5 | second SMT backend (subprocess) | pinned binary | `UVIL_CVC5` env var |
| ESBMC | model checking of C harnesses | `v8.5` binary | `UVIL_ESBMC` / PATH |
| Pantograph REPL | warm-backend pool (protocol v2) | built from `lean/pool/` | `UVIL_PANTOGRAPH` |
| Isabelle/HOL | HOL-twin attestation | Isabelle2025 bundle | `UVIL_ISABELLE` |

Pins are enforced: a present-but-mismatched tool version is a hard error,
never a silent check under the wrong kernel (`docs/decisions/0002-tool-pinning.md`).

## Examples

Two walk-throughs with exact inputs and outputs (captured on Windows with the
pinned tools; solver timings vary between runs, everything else is
deterministic). Both start from a fresh workspace (`uvil init`).

### Example 1: check a Boogie program, then re-check it incrementally

Input, `corpora/boogie/mod_reasoning.bpl`:

```boogie
// mod reasoning family
procedure mod_self(a: int, b: int)
  requires b == 3
{
  assert (a + b) % b == a % b;
}

procedure mod_double(a: int, b: int)
  requires b > 0
{
  assert (2 * a) % b == (a + a) % b;
}
```

`uvil check` imports the file (two procedures, one obligation each), encodes
each sequent as SMT-LIB2 (the context as assertions, the negated goal on top),
and asks z3:

```text
$ uvil check corpora/boogie/mod_reasoning.bpl
            verdicts (z3)
+------------------------------------+
| obligation       | status     | ms |
|------------------+------------+----|
| bc4beb84ee34c16a | discharged | 46 |
| fcb26ca8aadaa396 | discharged | 1  |
+------------------------------------+
run stored; ledger G1 appended (discharged=2)
```

What happened: for both obligations the probe `context ∧ ¬goal` came back
`unsat`, which is the single mapping point that produces `discharged`. The
verdicts, the updated obligations, and an I8 run are stored in the
content-addressed store, and a G1 entry (tool verdict, z3 5.1.0) is appended
to the hash-chained ledger.

`uvil check --incremental` on the unchanged input computes each obligation's
identity (a hash over spec, semantics model, program fragment, and profile
version, pinned to the backend and tool version), finds the cache empty, and
solves everything, storing the verdicts:

```text
$ uvil check corpora/boogie/mod_reasoning.bpl --incremental
incremental: 0 reused / 2 recomputed (merkle 8df6585bee7da045 -> 60fa156040484b9b)
            verdicts (z3)
+------------------------------------+
| obligation       | status     | ms |
|------------------+------------+----|
| bc4beb84ee34c16a | discharged | 12 |
| fcb26ca8aadaa396 | discharged | 0  |
+------------------------------------+
run stored; ledger G1 appended (discharged=2)
```

Running it again, nothing changed, so both identities hit the verdict cache:
no solver call happens (the `ms` column shows `-`), the Merkle root over the
obligation-identity set is unchanged, and the reused verdicts are still
recorded in the run and the ledger:

```text
$ uvil check corpora/boogie/mod_reasoning.bpl --incremental
incremental: 2 reused / 0 recomputed (merkle 60fa156040484b9b -> 60fa156040484b9b)
                 verdicts (z3)
+---------------------------------------------+
| obligation                | status     | ms |
|---------------------------+------------+----|
| bc4beb84ee34c16a (cached) | discharged | -  |
| fcb26ca8aadaa396 (cached) | discharged | -  |
+---------------------------------------------+
run stored; ledger G1 appended (discharged=2)
```

Only an exact identity match reuses a verdict, and only `discharged` verdicts
are cached; a changed spec, program, semantics model, profile, backend, or
tool version re-solves.

### Example 2: attest a Lean twin, then replay the attestation offline

`uvil check-lean` translates each obligation into a standalone Lean 4 theorem
and compiles it with the pinned toolchain (v4.33.1):

```text
$ uvil check-lean corpora/boogie/mod_reasoning.bpl --timeout-s 60
                  verdicts (lean4 4.33.1)
+---------------------------------------------------------+
| obligation       | status     | ms   | kernel           |
|------------------+------------+------+------------------|
| bc4beb84ee34c16a | discharged | 3953 | fcaef41ad6166e6c |
| fcb26ca8aadaa396 | open       | -    | -                |
+---------------------------------------------------------+
run stored; ledger G1 appended (1 kernel-attested; semantic-mismatch=1)
proof: uvil:proof@1:ac3df97f44bd64007a28a0fc935b26467a7011b2fed09b2886c90710240d06ab  (replay offline: uvil attest uvil:proof@1:ac3df97f44bd64007a28a0fc935b26467a7011b2fed09b2886c90710240d06ab)
```

What happened: the first obligation ports to the omega-provable subset (its
`%` divisor is pinned to the constant 3 by the context equality) and the Lean
kernel accepts the twin, so it is `discharged` with a proof artifact whose
`kernel_hash` is the SHA-256 of the proof file bytes plus the toolchain id.
The second does not: its divisor is a variable, outside the encoded subset,
so the encoder refuses it and the obligation stays `open` with a
`semantic-mismatch` diagnostic. That downgrade is measured and recorded, not
hidden; a failed proof search is never reported as a refutation.

Anyone with the pinned toolchain can replay the attestation offline; no UVIL
code participates in the verification:

```text
$ uvil attest uvil:proof@1:ac3df97f44bd64007a28a0fc935b26467a7011b2fed09b2886c90710240d06ab
                     attestation replay (leanprover/lean4:v4.33.1)
+--------------------------------------------------------------------------------------+
| check             | result                                                           |
|-------------------+------------------------------------------------------------------|
| kernel exit-0     | ok                                                               |
| kernel hash match | ok                                                               |
| kernel_hash       | fcaef41ad6166e6ceb37929205118c2ca4dcfd4588909485dc04985f6c746d60 |
+--------------------------------------------------------------------------------------+
attestation verified; the pinned kernel accepts this proof file offline
```

The replay re-runs the pinned kernel on the stored proof file and checks both
that it exits 0 and that the recomputed hash matches the recorded one.

## Getting started

Install from the repository root:

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip ...
```

Check a Boogie program end-to-end (import to obligations to z3 to verdicts
and a ledger entry):

```sh
uvil init
uvil check corpora/boogie/mod_reasoning.bpl
# run stored; ledger G1 appended (discharged=2)
```

Run the same check incrementally; the second invocation reuses cached
verdicts and performs no solver calls:

```sh
uvil check corpora/boogie/mod_reasoning.bpl --incremental
uvil check corpora/boogie/mod_reasoning.bpl --incremental
# incremental: 2 reused / 0 recomputed (merkle <old> -> <new>)
```

Attest a Lean twin with the pinned kernel, then replay the attestation
offline (no UVIL code participates in the verification):

```sh
uvil check-lean corpora/boogie/mod_reasoning.bpl
# proof: uvil:proof@1:<hash>  (replay offline: uvil attest uvil:proof@1:<hash>)
uvil attest uvil:proof@1:<hash>
# attestation verified; the pinned kernel accepts this proof file offline
```

Run the benchmark and the corpus integrity checks:

```sh
uvil bench --corpus corpora/churn --state .uvil-bench          # metrics table, exit 1 on target miss
uvil corpus verify corpora/boogie                              # identities without solving
python examples/repair_loop/experiment.py                      # two-arm repair experiment
```

Work with individual artifacts and the ledger:

```sh
uvil put examples/vec_push/obligation.json     # validate + store, prints artifact id
uvil get uvil:obligation@1:<hash>              # fetch back, byte-identical
uvil schema obligation                         # JSON Schema for an artifact type
uvil shadows spec.json                         # R4 vacuity probes over a spec's shadow set
uvil render uvil:counterexample@1:<hash> --form human
uvil ledger verify                             # hash-chain tamper evidence
```

End-to-end demos with walk-throughs live in `examples/` (`vec_push`,
`dafny_to_cvc5`, `lean_attest`, `repair_loop`, `forge_on_uvil`); the versioned
corpora are documented in `corpora/README.md`.

## License

Distributed under the Apache License 2.0; see `LICENSE`.

## References

1. J. Wu, R. J. George, A. Anandkumar. ITPEval: Benchmarking Formal
   Translation Across Interactive Theorem Provers. arXiv:2607.19407 (2026).
2. C. Bobot, J.-C. Filliâtre, C. Marché, A. Paskevich. Why3: Divide Your
   Program and Conquer. VSTTE 2011.
3. C. Barrett, P. Fontaine, C. Tinelli. The SMT-LIB Standard: Version 2.6.
   Technical report, University of Iowa.

