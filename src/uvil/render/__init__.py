"""uvil.render - I6/I7 renderers: common JSON (machine) + human text + backend-native.

The renderers are producer-agnostic: they consume frozen `@1` artifact models
only, so Trace/Scenario/CounterSpec I6s render identically no matter which
adapter (M2 fixtures, shadow evaluator, or the M4 ESBMC producer) built
them. Nothing here touches artifact schemas; renders are plain dicts/strings.

Backend-native renders dispatch per I6 kind (M4): `valuation` ->
`render/smt.py` (SMT-LIB model text), `trace` -> `render/esbmc.py` (ESBMC
report text); `scenario`/`counterspec` have no backend producer yet and stay
loud NotImplementedErrors.
"""

from __future__ import annotations

from ..artifacts import Counterexample
from .common import to_common_json
from .esbmc import to_backend_render as _esbmc_render
from .human import to_human
from .smt import to_backend_render as _smt_render

__all__ = ["to_backend_render", "to_common_json", "to_human"]


def to_backend_render(cex: Counterexample) -> str:
    """Dispatch an I6 to its backend-native render (M4: SMT + ESBMC)."""
    if cex.kind == "valuation":
        return _smt_render(cex)
    if cex.kind == "trace":
        return _esbmc_render(cex)
    raise NotImplementedError(
        f"no backend render for counterexample kind={cex.kind!r}: Scenario "
        "renders arrive with a TLC adapter, CounterSpec with a spec-repair "
        "consumer (fail loud, never approximate)"
    )
