# ADR 0006: guarantee-class semantics, R2 descope, taxonomy-wording errata

- Status: accepted
- Date: 2026-09-09
- Deciders: UVIL maintainers
- Amends: the draft (§4.5 G-table, §4.2 I7 kinds), M1's translator schedule

## Context

A 2026-09-09 audit of the M1–M4 plans against the shipped code found three
drifts worth putting on the record: the draft's §4.5 guarantee-class table
described G1/G2 more narrowly than the implementation; M1 promised the full
spec-strength translator "lands M4", which did not happen; and artifact
docstrings claimed the I7 diagnostic kinds are structurally "aligned" with
Strata's verification-mode taxonomy, which overstates the relationship.

## Decision

1. **Guarantee-class semantics (amends draft §4.5 to match the code; zero
   ledger churn).** `GUARANTEE_CLASSES` (G0–G4, `ledger/journal.py`) keep
   their identifiers; the *semantics* recorded here are the implementation's:
   - **G0** — no guarantee (imported/opaque/unknown provenance).
   - **G1** — a **tool verdict** (solver verdict, model-checking run record —
     e.g. the ESBMC G1 of ADR 0004, which carries no kernel hash because no
     kernel participates) **or kernel attestation** (a Lean kernel-checked
     proof). The draft's narrower "kernel attestation only" reading is
     corrected: the tool-verdict arm is first-class.
   - **G2** — kernel-attested G1 **plus** kernel-checked
     statement-faithfulness evidence (the BEq check; `check/shadows.py`).
     The shadows-validated variant of G2 is deferred.
   - **G3/G4** — defined and accepted by the API but **not yet produced by
     any code path** (scheduled M5+/P5). Their presence in
     `GUARANTEE_CLASSES` is intentional (forward-compatible identifiers),
     not an implementation gap to close early.
2. **R2 descope (decision of 2026-09-09).** The full spec-strength
   translator — M1's "lands M4" promise — is **formally descoped to M5+**
   (executed there as a master-plan M5 scope item; see also the draft P4.1
   note). R2 remains what it is today: the enforcement hook
   (`adapters/smt/r2.py`) plus the shadow evaluator (`check/shadows.py`),
   not a translator. The D1 verified translator (M4) formalizes the
   target-language (LIA) semantics in Lean only.
3. **Taxonomy-wording errata.** The I7 kinds
   (`{unproved, vacuous, timeout, parse, semantic-mismatch, unknown}`) are
   **inspired by** Strata's verification-mode/severity taxonomy (legacy
   `VerificationModes.md` — deprecated upstream, whose canonical reference
   is now `verso/TransformsDoc.lean`), **not structurally aligned** with it:
   `parse` and `semantic-mismatch` have no Strata counterpart, and the
   Strata document classifies check outcomes (pass/error/note/warning across
   `deductive`/`bugFinding`/`bugFindingAssumingCompleteSpec` modes), not
   failure kinds. Docstrings and prose are softened accordingly; no
   artifact/schema changes (the M2 schema freeze, ADR 0001, is unaffected).

## Consequences

- draft.md §4.5/§4.2/I6/P1.3/P4.1 are amended surgically (table rows +
  one-line notes) to match the implementation; the draft keeps its voice
  and status-marking convention.
- Any future G1-semantics change (e.g. requiring kernel hashes for all G1)
  is a ledger-semantics break and needs a new ADR plus a migration note —
  the ledger is append-only.
- The Strata relationship is documented as inspiration-with-caveat
  (import-only frontend, vendor-TCB caveat of M4); no normative claim of
  structural alignment remains.
