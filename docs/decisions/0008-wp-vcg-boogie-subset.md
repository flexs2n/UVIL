# ADR 0008: WP VCG for the Boogie subset — semantics change, identity amendment, M1 retirement

- Status: accepted
- Date: 2026-09-10
- Deciders: UVIL maintainers
- Records: the review's W2 fix (priority work item WI-1); amends draft §5.6's
  obligation-identity tuple; supersedes the M1 VC approximation

## Context

The Boogie importer's obligation generation was the documented **M1
approximation** (`origin_backend="boogie-m1"`): per-assert goals over a context
of preconditions, axioms, explicit assumes, and loop invariants *assumed
without proof*. Assignments contributed nothing. The approximation had a real
soundness hole: an unproven (even false) loop invariant acted as an unjustified
assumption, so an obligation could be discharged that Boogie's real VCG would
refute — e.g. `while i < n invariant i == n { i := i + 1; } assert i == n` was
reported `discharged` with the false invariant in context. Havoc'd variables
were handled by dropping assumptions mentioning them, which is neither precise
nor a renaming discipline.

## Decision

1. **The WP VCG replaces the M1 path outright** (`adapters/boogie/vcgen.py`).
   Obligations are sound weakest-precondition sequents computed by a forward
   symbolic walk (Boogie's passive form), recorded as
   `origin_backend="boogie-wp"`:
   - assignments substitute into downstream goals (reusing the
     quantifier-shadowing-honoring `substitute`);
   - `a[i] := v` becomes a `store`/`seq.update` term at the use site;
   - `havoc x` and loop exits rename the variable to a fresh free variable
     `<name>!<n>` (`!` is outside the Boogie identifier charset, so collisions
     are impossible). A fresh free variable is implicitly universally
     quantified by the SMT validity check — exactly havoc semantics, with no
     quantifier in the term encoding;
   - `assert A` folds `A` into the path (asserts are guards downstream);
     `assert A by { B }` proves A under B's assumptions;
   - `while G invariant I1..In` emits initiation
     (`path ⊢ I1 ∧ .. ∧ In`) and preservation
     (`path, I@head, G ⊢ I@end`) obligations; the exit frame renames
     body-modified variables fresh and assumes `I@exit ∧ ¬G` downstream. A
     loop with no invariants emits no init/preservation obligations;
   - `return;` marks the rest of the block unreachable (`false` on the path:
     downstream obligations are vacuous);
   - `if`/`call` remain out-of-subset (fail loud, unchanged); `ensures`
     clauses stay recorded-in-I2-only (no exit obligations).
   The pinned shapes are the discovery tests (`tests/test_vcgen.py`), written
   and hand-computed before the implementation; the W2 counterexample above is
   committed there as a red-turned-green test.
2. **Obligation identity is amended** (`store/identity.py`): the identity
   payload gains the obligation's **canonical sequent** — the goal plus the
   context with its ORDER normalized away. Motivation: one procedure now emits
   several obligations (initiation/preservation/assert) sharing the M0 tuple
   `(spec, semantics_model, program_fragment, profile_version)`, and the
   verdict cache keyed by that tuple alone would reuse a `discharged` verdict
   for a *refuted* obligation of the same procedure — unsound. Order
   normalization keeps the churn benchmark's `no-op-reorder` control a cache
   hit (pure formatting churn moves nothing in the canonical form). Draft §5.6
   is amended accordingly; every identity-keyed corpus manifest
   (`boogie/`, `lean/`, `isabelle/`) was regenerated in the same event.
3. **Corpus discipline is per obligation.** `tools/gen_corpus.py` observes and
   records a status per obligation identity; the designed-verdict check is
   `discharged` ⇒ every obligation discharges, `refuted` ⇒ at least one does
   (loop families legitimately mix). All five identity/status-bearing corpora
   (`boogie`, `failures`, `churn`, `lean` slice, `isabelle` slice) were
   regenerated under WP identities with re-observed verdicts; the
   generator-fails-on-disagreement discipline is unchanged.
4. **M1 is retired.** The `boogie-m1` origin, the approximation path, and its
   documentation are deleted; the parser is syntax-only again. Parse-error
   messages keep their verbatim-line behavior (unchanged).

## Consequences

- Verdicts for programs with assignments/havoc/loops change where the M1
  approximation was unsound or imprecise; those are the intended semantics
  changes (e.g. `x := x + 1; assert x >= 1` now discharges).
- Cache keys change (new identity payload); older caches fail safe (miss and
  re-solve) without a protocol-version bump.
- No artifact schema changed: identity is derived data (`store/`), origin
  backends are data, and the nine schemas are byte-identical (the schema guard
  stays green).
- The corpus grew from ~530 to 591 identities (loop procedures contribute
  their extra VCs).
