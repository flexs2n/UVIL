# Lean attestation demo (M3)

SMT discharge + Lean twin attestation + offline replay, end to end.

```
# 0. workspace
uvil init

# 1. Boogie in -> obligations -> z3 discharges (ledger G1, solver-verdict)
uvil check examples/lean_attest/push.bpl

# 2. the same obligations -> generated Lean twins -> pinned-kernel attestation
#    (ledger G1 with kernel hashes; add evidence for G2 with a BEq probe)
uvil check-lean examples/lean_attest/push.bpl
# -> prints `proof: uvil:proof@1:<hash>` lines

# 3. replay an attestation OFFLINE - only the pinned Lean kernel verifies
#    the stored proof file:
uvil attest uvil:proof@1:<hash>

# tampering is detected: modify the stored payload, re-attest -> exit 1
```

Requirements: elan with the pinned toolchain (`lean/lean-toolchain`,
`leanprover/lean4:v4.33.1`). Without elan, `check-lean`/`attest` skip
cleanly (exit 0) - the SMT path above is unaffected.

Guarantee classes seen in this demo:
- step 1: **G1** (solver verdict, no certificates - ADR 0002)
- step 2: **G1** (kernel attestation; **G2** when the run carries
  kernel-checked statement-faithfulness evidence, i.e. a BEq biconditional
  accepted by the same kernel)

R1 in practice: UVIL records the kernel's verdict and the exact proof-file
bytes; it never re-verifies kernel work. The recorded `kernel_hash`
(sha256 over the proof-file bytes + toolchain id) lets anyone detect
tampering and replay the check with the pinned toolchain alone.
