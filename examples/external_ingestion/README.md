# Demo: external-artifact ingestion (WI-2, the W5 fix)

Third-party verification programs flow through UVIL's pipeline end to end:

    upstream Boogie test (verbatim) -> import (WP lowering) -> z3 verdict
    -> Lean twin (omega) -> pinned-kernel attestation -> `uvil attest` replay

This is the first externally-authored obligation set the backends have ever
consumed (the Strata upstream demo, by contrast, yielded zero obligations).

## What is committed

- `upstream/*.bpl` — 50 verbatim files from the pinned boogie-org/boogie
  checkout (MIT; `PROVENANCE.json` records the URL, commit hash, and
  license). These are exactly the upstream test files that import cleanly
  into the subset and yield obligations — selected by the importer's honest
  outcome over the FULL upstream scan (765 files scanned, 637 out-of-subset:
  measured in `PROVENANCE.json`, not hidden).
- `upstream_out/*.bpl` — a deterministic 10-file sample of the out-of-subset
  remainder. Each one fails the import LOUDLY (I7 `parse` diagnostics with
  the verbatim source line); the pinned outcomes are the honest downgrade
  record.
- `lean/*.lean` — the rendered Lean twins (`by omega`) for the encodable
  obligations, each attested by the pinned kernel at generation time.
- `expected.json` — per-file import outcomes, per-obligation observed z3
  statuses (53 discharged / 38 refuted / 8 open - external tests assert both
  sides), and the Lean-twin downgrade metrics (23 semantic-mismatch, rate
  0.1949 - terms outside the omega-provable subset fail loud, never silent
  mistranslations).

## Regenerate

```sh
python tools/fetch_external.py        # one-time network fetch (pinned commit)
python tools/gen_external_slice.py    # offline: z3 + Lean over committed copies
```

## Verify

```sh
pytest tests/test_external.py         # manifest, verdicts, hashes (offline)
```

Per-obligation verdicts re-solve with the pinned z3 and must match
`expected.json`; the recorded kernel hashes recompute from the committed
theorem bytes.

## Offline attestation replay

```sh
uvil attest corpora/external/lean/uvil_obl_01901d94c1e5.lean
```

The pinned Lean kernel re-checks the theorem file offline; with
`--expect-hash <kernel_hash>` the recorded attestation is verified too.
