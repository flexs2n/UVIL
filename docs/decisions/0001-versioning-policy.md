# ADR 0001: Versioning policy — artifact schemas frozen at `@1`

- Status: accepted
- Date: 2026-09-08
- Deciders: UVIL maintainers

## Context

UVIL artifacts (I1–I9) are content-addressed: `artifact_id = "uvil:<type>@<version>:<hash>"`.
Any change to canonical serialization or field semantics changes every downstream hash and
invalidates cached obligation identities and corpora. The draft (§5, principle P2) mandates
"dialect profiles over a monolithic language" and slow core evolution.

## Decision

1. Each artifact type carries a `schema_version` class attribute, currently `"1"`.
2. The set of schemas `uvil.*.schema.json` is **frozen at version `@1` once M1 lands**.
   After freezing: adding optional fields requires a new minor profile, not a core bump;
   any breaking change bumps the version and dual-writes adapters during transition.
3. Canonical serialization is JCS-style: UTF-8 JSON, sorted keys, no insignificant
   whitespace (`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).
   This is a hard compatibility contract — changing it invalidates all stored artifacts.
4. Tool-specificity is absorbed by named dialect profiles (`uvil.dafny@1`, `uvil.verus@1`, …),
   which evolve faster than the core. Profiles are referenced by `target_profile` on I4.
5. Obligation identity = `sha256(canonical(spec, semantics_model, program_fragment, profile_version))`.
   This tuple is the M5 incremental-protocol cache key; changing it invalidates all corpora.

## Consequences

- Golden tests must be per pinned tool version (Boogie/Dafny/Lean/z3/cvc5), because
  backend VC extraction is brittle across versions; the UVIL layer itself is pinned by
  the schema freeze.
- The ledger records the schema version of every referenced artifact, so old journals
  remain verifiable after future schema evolution.
