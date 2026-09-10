# lean/ — Lean workspace (M3 + M4)

- `lean-toolchain` — the pinned toolchain (`leanprover/lean4:v4.33.1`, ADR 0002 /
  0003). The primary check path needs ONLY this file + elan: no Lake, no Mathlib.
- `UVIL/Core.lean` — the D1 verified-translator core (M4): the shared-theory Term
  AST as a deep embedding, the deep-embedded LIA target language
  (`mulLit`/`divConst`/`modConst` encode the subset restrictions in their
  syntax), the `encodeLia` translator, and the **preservation theorem**
  `Term.encodeLia_preserves` (`interp (encodeLia t) env = eval t env` — closed-term
  semantics preserved through the translator). Python mirror:
  `src/uvil/translate.py`; evidence recording: `uvil.check.translator`
  (kernel-checked I9 + G1); scope: LIA subset only (M5+ for anything else).
- `UVILTranslateProve.lean` — the `uvil-translate-prove` parity runner (consumes
  the s-expression fixture format on stdin; used by tests/test_translator.py).
- `lakefile.toml` — the root Lake project (no external dependencies):
  `cd lean && lake build UVIL uvil-translate-prove`.
- `pool/lakefile.toml` — OPTIONAL separate project for the Pantograph warm
  pool (`src/uvil/adapters/lean/pool.py`, enabled via `UVIL_PANTOGRAPH`).
  Kept separate in M4: a broken optional dependency must not block the D1
  targets. Re-pinned 2026-09-09 to the canonical mirror
  `leanprover/Pantograph` @ `dev` head `92d4818` (the old
  `streesha/pantograph` @ `master` pin was invalid - repo 404).

## Build the D1 targets

```
cd lean
lake build UVIL uvil-translate-prove
```

## Build the warm pool (optional)

```
cd lean/pool
lake update
lake build Pantograph repl
```

Build-probe status (2026-09-09): the pinned Pantograph dev head builds
cleanly on Windows under the shared `v4.33.1` toolchain, and the pool is
wired end-to-end (M5):

- the binary is `.lake/packages/Pantograph/.lake/build/bin/repl.exe`
  (named `repl`, not `pantograph-repl`); on Windows, put
  `~/.elan/toolchains/leanprover--lean4---v4.33.1/bin` on `PATH` first
  (the exe needs `libleanshared.dll`) — the live-arm tests set this
  themselves.
- `pool.py` speaks **protocol v2** (discovery-pinned on the wire, 2026-09-09):
  launch with the `Init` import argument (a bare REPL environment is empty);
  the REPL prints a `ready.` banner; commands are
  `{"cmd": ..., "payload": {...}}` JSON lines (`stat` liveness; `goal.start`
  takes a statement TERM, not a full theorem source; `goal.tactic` runs the
  single-tactic body; success = `nextStateId` present + empty `goals` +
  `hasSorry`/`hasUnsafe` false + `rootHasSorry` false).
- **Live-arm outcome (2026-09-09):** `tests/test_lean_pool.py` run with
  `UVIL_PANTOGRAPH` pointed at the built binary passes 16/16 — the pool
  attests a real theorem through the pinned kernel and the sorry gate
  correctly fails a `sorry`-tainted proof (never attested).
