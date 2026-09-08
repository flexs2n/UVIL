# Demo slice: vec push capacity obligation

The M0 exit demo: a minimal I1→I2→I3→I4 chain, hashed and stored.

```sh
uvil init
uvil put examples/vec_push/intent.json examples/vec_push/spec.json \
         examples/vec_push/program.json examples/vec_push/obligation.json
uvil ledger append --ref uvil:obligation@1:... --guarantee G0
uvil ledger verify
uvil roots
```

What this demonstrates:

- I1–I4 artifacts serialize canonically (sorted keys, no whitespace) and are
  content-addressed as `uvil:<type>@<version>:<sha256>`.
- The obligation's sequent is written in the core assertion language
  (`uvil.core.int` terms); the spec carries a shadow set (R4) and references the
  registered semantics model `model:why3-memory.v1`.
- The guarantee ledger records provenance with hash-chain tamper evidence.
