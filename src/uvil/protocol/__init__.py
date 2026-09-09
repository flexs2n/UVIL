"""uvil.protocol - the M5 incremental check protocol.

Verdict cache (`cache.py`), cache-partitioned incremental checking with
Merkle-diff evidence (`incremental.py`), and the churn benchmark harness
(`bench.py`, M5 commit 3).
"""

from __future__ import annotations

from .cache import PROTOCOL_VERSION, CacheEntry, VerdictCache, cache_key
from .incremental import IncrementalResult, check_incremental, obligation_cache_identity

__all__ = [
    "PROTOCOL_VERSION",
    "CacheEntry",
    "IncrementalResult",
    "VerdictCache",
    "cache_key",
    "check_incremental",
    "obligation_cache_identity",
]
