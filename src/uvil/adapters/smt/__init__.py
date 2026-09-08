"""SMT adapter: I4 sequents -> SMT-LIB2, real solver verdicts, I6 counterexamples.

Layout:
- `encode`   - deterministic SMT-LIB2 emission via `uvil.artifacts.terms.to_smt`.
- `backends` - in-process z3 (pinned) and optional subprocess cvc5.
- `cex`      - solver models -> I6 `Valuation` counterexamples.
- `r2`       - R2 spec-strength enforcement hook (API; full translator is M4).
"""
