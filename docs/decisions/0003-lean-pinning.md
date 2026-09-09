# ADR 0003: Lean pinning — toolchain, Pantograph boundary, and div/mod semantics

- Status: accepted
- Date: 2026-09-08
- Deciders: UVIL maintainers
- Extends: 0002 (tool pinning)

## Context

M3 adds a Lean 4 adapter: obligations discharged in SMT get generated Lean
twins that the pinned kernel attests (I5 proofs, ledger G1/G2), with offline
replay. Three tool-shaped decisions need fixing: the toolchain pin, the role
of Pantograph, and integer division semantics.

## Decision

1. **Lean is pinned via `lean/lean-toolchain`** = `leanprover/lean4:v4.33.1`
   (installed natively via elan; Lean 4 ships Windows toolchains). The
   `PINNED_LEAN` constant mirrors the pin:
   - a present-but-different toolchain is a **hard error**
     (`LeanVersionMismatch`) — never a silent check under the wrong kernel;
   - a fully absent toolchain raises `LeanNotInstalled`: CLI paths skip
     cleanly (exit 0), tests self-skip (Dafny precedent).
2. **Attestation = plain `lean` compile (exit 0)** of a standalone,
   self-contained theorem file. `kernel_hash = sha256(proof-file bytes +
   toolchain id)`; the stored I5 `inline` payload is byte-identical to the
   proof file, so anyone with the pinned toolchain can replay the
   attestation offline (`uvil attest`) — no UVIL code, no network, no
   solver. UVIL records kernel work; it never re-verifies it (R1).
3. **Pantograph is optional infrastructure** for the warm-backend pool
   (`UVIL_PANTOGRAPH` → built REPL binary; skip-if-absent, cvc5 precedent).
   It gates only performance (persistent sessions vs per-batch cold start) —
   the exit criterion needs zero Pantograph. The optional Lake project lives
   in `lean/` and does not build on Windows today. LeanDojo is excluded
   (Linux/Docker-only).
4. **div/mod semantics (the honest-subset rule).** Discovery on the pinned
   toolchain showed Lean's `Int /`/`%` are floored (`(-7)/2 = -4`,
   `(-7)%2 = 1`) — they match SMT-LIB Euclidean `div`/`mod` for positive
   divisors. The encoder therefore supports `/`/`%` ONLY with a
   provably-positive constant divisor, obtained by constant-pin propagation
   of context equalities `var == K` (the generated divmod corpus family);
   curated `requires b > 0` entries (variable divisor) fall out of the slice
   as `semantic-mismatch` I7s — measured in the slice manifest's downgrade
   metrics, never hidden. Discovery also pinned: a parenthesized
   `∀`-prefixed statement is invisible to `omega` (binders are hoisted into
   theorem parameters in the BEq probe), Bool atoms work only as direct
   literal-coerced facts, and quantified hypotheses discharge only with
   simple comparison bodies.

## Consequences

- Upgrading Lean is a deliberate, reviewable change: bump
  `lean/lean-toolchain` + `PINNED_LEAN`, re-run discovery, regenerate the
  slice (`tools/gen_lean_slice.py`) and its golden snapshots.
- CI may omit elan: Lean tests self-skip until runners preinstall the pin.
- The slice's offline-replay property depends on byte-stable Lean files
  (`.gitattributes` forces LF; the generator writes bytes, never text).
