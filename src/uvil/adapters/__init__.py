"""Boogie import adapter: Boogie/Dafny text -> I4 obligations (M1).

Layout:
- `parser` - pure-Python recursive-descent parser for a *documented Boogie subset*.
- `lower`  - parse result -> I2/I3/I4 artifacts (+ I7 diagnostics, fail-loud).
- `dafny`  - pinned-version Dafny wrapper emitting Boogie text into the same parser.
"""

from __future__ import annotations
