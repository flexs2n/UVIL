"""uvil.render - I6/I7 renderers: common JSON (machine) + human text + backend-native.

The renderers are producer-agnostic: they consume frozen `@1` artifact models
only, so Trace/Scenario/CounterSpec I6s render identically no matter which
adapter (M2 fixtures, shadow evaluator, or the M4 ESBMC/TLC producers) built
them. Nothing here touches artifact schemas; renders are plain dicts/strings.
"""

from __future__ import annotations

from .common import to_common_json
from .human import to_human
from .smt import to_backend_render

__all__ = ["to_backend_render", "to_common_json", "to_human"]
