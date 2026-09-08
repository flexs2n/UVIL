# Corpora

Versioned corpora of obligations, failures, and expected verdicts.

Populated from M1 onward: ≥500 obligations harvested from VeriContest artifacts
(arXiv:2605.08553) and Dafny benchmarks, with expected verdicts and golden
SMT-LIB2 / counterexample snapshots. See the master plan, M1 §4 and M2 §2.

Corpus files are artifacts in the UVIL store format (content-addressed JSON with
an `uvil_type` envelope) and are validated against the checked-in schemas.
