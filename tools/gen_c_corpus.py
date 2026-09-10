"""Deterministic C harness corpus generator (M4).

Families (>= 50 entries, all committed; regeneration is idempotent and
deterministic - identical inputs reproduce byte-identical files):

- `safe-assert` (15)      guarded identities; ESBMC verdict: verified; import:
  obligations (in-subset asserts)
- `overflow` (10)         asserts violated through C 32-bit wraparound or
  arithmetic; verdict: violated; import: obligations
- `div-zero` (5)          unguarded division by a nondeterministic divisor -
  ESBMC's internal division-by-zero check fires; verdict: violated; import:
  obligations (the guarded companion assert is in-subset)
- `bounds` (10)           unguarded array indexing - ESBMC's internal
  array-bounds check fires; verdict: violated; import: OUT OF SUBSET (arrays
  are not in the sequent language; I7 parse with the verbatim line)
- `pointer-heap` (5)      malloc/deref patterns verified/violated through
  ESBMC's own pointer semantics (no Boogie lowering exists - the
  cross-language case); verdict: verified/violated; import: OUT OF SUBSET
- `deep` (5, slow)        deep nonlinear recurrence chains - the bit-blasted
  solver query exceeds the subprocess budget; verdict: timeout; import: OUT
  OF SUBSET (loop bounds exceed the unroll budget)

`expected.json` records per entry: `{file, family, expected, import}` where
`expected` is the pinned binary's verdict at generation time (ESBMC 8.5.0,
release tag v8.5) and `import` says what `import_c` must do. Verdicts are
model-checking run records - they never discharge or refute deductive
obligations.

The safe/overflow/div-zero obligation sequents are honest under the
documented bounded-integer abstraction (they avoid wraparound-dependent
claims in sequent position; wraparound-induced violations live in the
overflow family where ESBMC's C semantics decide).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.esbmc.import_c import import_c  # noqa: E402

C_CORPUS = REPO_ROOT / "corpora" / "c"
EXPECTED_PATH = C_CORPUS / "expected.json"

ESBMC_PIN = "8.5.0"
RELEASE_TAG = "v8.5"

HEADER = "#include <stdlib.h>\n#include <assert.h>\n\n"


@dataclass(frozen=True)
class Entry:
    stem: str
    family: str
    expected: str  # verified | violated | timeout (the ESBMC verdict)
    import_kind: str  # obligations | out-of-subset
    source: str


def _harness(body: str) -> str:
    return f"{HEADER}int main(void) {{\n{body}}}\n"


def _safe_entries() -> list[Entry]:
    programs = [
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 0 && x < 100) {\n    assert(x < 100);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 0) {\n    assert(x - x == 0);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 7) {\n    assert(x - 7 >= 0);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x <= 42) {\n    assert(x + 1 <= 43);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 0 && x % 2 == 0) {\n    assert((x / 2) * 2 == x);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 0 && x <= 1000) {\n    assert((x / 3) * 3 + x % 3 == x);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  int y = x + 1;\n  int z = y + 1;\n  if (x >= 0) {\n    assert(z == x + 2);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x > 0) {\n    assert(x != 0);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= -50 && x <= 50) {\n    assert(x <= 50);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x == 5) {\n    assert(x + 0 == 5);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x > 0) {\n    if (x < 10) {\n      assert(x < 20);\n    }\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 0) {\n    assert(x >= 0);\n  } else {\n    assert(x < 0);\n  }\n  return 0;\n",
        "  int s = 0;\n  for (int i = 0; i < 5; i++) {\n    s = s + 1;\n  }\n  assert(s == 5);\n  return 0;\n",
        "  int s = 0;\n  for (int i = 0; i < 4; i++) {\n    s = s + i;\n  }\n  assert(s == 6);\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x <= 2147483000) {\n    assert(x + 100 <= 2147483647);\n  }\n  return 0;\n",
    ]
    return [
        Entry(f"safe_{i:03d}", "safe-assert", "verified", "obligations", _harness(p))
        for i, p in enumerate(programs)
    ]


def _overflow_entries() -> list[Entry]:
    programs = [
        "  int x = __VERIFIER_nondet_int();\n  if (x > 2147483640) {\n    assert(x + 7 > x);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x < -2147483000) {\n    assert(x - 100 < x);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x > 46340) {\n    assert(x * x > 0);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x > 10) {\n    assert(x <= 10);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x != 7) {\n    assert(x == 7);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  int y = x + 1;\n  if (x == 2147483647) {\n    assert(y > x);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 1000) {\n    assert(x / 2 < 100);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x > 0 && x < 100) {\n    assert(x % 10 != 5);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x <= -2) {\n    assert(x + 1 >= 0);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  if (x >= 3 && x <= 6) {\n    assert(x * x != 25);\n  }\n  return 0;\n",
    ]
    return [
        Entry(f"overflow_{i:03d}", "overflow", "violated", "obligations", _harness(p))
        for i, p in enumerate(programs)
    ]


def _divzero_entries() -> list[Entry]:
    bodies = [
        "  int d = __VERIFIER_nondet_int();\n  int z = 42 / d;\n  if (d != 0) {\n    assert(z == 42 / d);\n  }\n  return 0;\n",
        "  int d = __VERIFIER_nondet_int();\n  int z = 100 / d;\n  if (d != 0) {\n    assert(z <= 100);\n  }\n  return 0;\n",
        "  int d = __VERIFIER_nondet_int();\n  int z = d / d;\n  if (d != 0) {\n    assert(z == 1);\n  }\n  return 0;\n",
        "  int d = __VERIFIER_nondet_int();\n  int z = 42 % d;\n  if (d != 0) {\n    assert(z < 42);\n  }\n  return 0;\n",
        "  int x = __VERIFIER_nondet_int();\n  int d = __VERIFIER_nondet_int();\n  int z = x / d;\n  if (d != 0) {\n    assert(z == x / d);\n  }\n  return 0;\n",
    ]
    return [
        Entry(f"divzero_{i:03d}", "div-zero", "violated", "obligations", _harness(p))
        for i, p in enumerate(bodies)
    ]


def _bounds_entries() -> list[Entry]:
    bodies = [
        "  int a[10];\n  int i = __VERIFIER_nondet_int();\n  a[i] = 5;\n  return a[i];\n",
        "  int a[10];\n  int i = __VERIFIER_nondet_int();\n  int z = a[i];\n  return z;\n",
        "  int a[10];\n  a[-1] = 1;\n  return 0;\n",
        "  int a[10];\n  a[10] = 1;\n  return 0;\n",
        "  int a[10];\n  for (int i = 0; i < 20; i++) {\n    a[i] = i;\n  }\n  return 0;\n",
        "  int a[10];\n  int i = __VERIFIER_nondet_int();\n  a[i + 3] = 1;\n  return 0;\n",
        "  int a[4];\n  int x = __VERIFIER_nondet_int();\n  int y = __VERIFIER_nondet_int();\n  a[x * y] = 1;\n  return 0;\n",
        "  char buf[4];\n  int i = __VERIFIER_nondet_int();\n  buf[i] = 'x';\n  return 0;\n",
        "  int a[8];\n  int b[8];\n  int i = __VERIFIER_nondet_int();\n  a[i] = 1;\n  b[i] = 2;\n  return a[i] + b[i];\n",
        "  int a[10];\n  int i = __VERIFIER_nondet_int();\n  a[2 * i] = 1;\n  return 0;\n",
    ]
    return [
        Entry(f"bounds_{i:03d}", "bounds", "violated", "out-of-subset", _harness(p))
        for i, p in enumerate(bodies)
    ]


def _pointer_entries() -> list[Entry]:
    bodies = [
        # null-checked store/load through a pointer: ESBMC's pointer checks pass
        "  int *p = (int *)malloc(sizeof(int));\n  if (p != 0) {\n    *p = 5;\n    int z = *p;\n    assert(z == 5);\n  }\n  free(p);\n  return 0;\n",
        # two-node linked list
        "  struct node { int v; struct node *next; };\n  struct node *b = (struct node *)malloc(sizeof(struct node));\n  struct node *a = (struct node *)malloc(sizeof(struct node));\n  if (a != 0 && b != 0) {\n    a->v = 1;\n    b->v = 2;\n    a->next = b;\n    b->next = 0;\n    assert(a->next->v == 2);\n  }\n  free(a);\n  free(b);\n  return 0;\n",
        # heap array with a guarded index
        "  int *p = (int *)malloc(10 * sizeof(int));\n  if (p != 0) {\n    for (int i = 0; i < 10; i++) {\n      p[i] = i;\n    }\n    assert(p[9] == 9);\n  }\n  free(p);\n  return 0;\n",
        # use after free: ESBMC's invalidated-dynamic-object check fires
        "  int *p = (int *)malloc(sizeof(int));\n  free(p);\n  int z = *p;\n  return z;\n",
        # unchecked malloc: the null-dereference check fires
        "  int *p = (int *)malloc(sizeof(int));\n  *p = 5;\n  int z = *p;\n  free(p);\n  return z;\n",
    ]
    expected = ["verified", "verified", "verified", "violated", "violated"]
    return [
        Entry(f"pointer_{i:03d}", "pointer-heap", e, "out-of-subset", _harness(p))
        for i, (p, e) in enumerate(zip(bodies, expected, strict=True))
    ]


def _deep_entries() -> list[Entry]:
    # solver-hardness harnesses: deep nonlinear (mod/mult) recurrence chains
    # over nondeterministic seeds - the bit-blasted query exceeds any
    # reasonable subprocess budget (expected verdict: timeout, recorded with
    # the pin's observed budgets); loop bounds exceed the unroll budget, so
    # import is out-of-subset
    bodies = [
        (
            "  int a = __VERIFIER_nondet_int();\n  int s = 7;\n  for (int i = 0; i < 30; i++) {\n    s = (s * 31 + a) % 1000003;\n  }\n  assert(s != 42);\n  return 0;\n"
        ),
        (
            "  int a = __VERIFIER_nondet_int();\n  int s = 3;\n  for (int i = 0; i < 28; i++) {\n    s = (s * 37 + a) % 999983;\n  }\n  assert(s != 7);\n  return 0;\n"
        ),
        (
            "  int a = __VERIFIER_nondet_int();\n  int s = 13;\n  for (int i = 0; i < 32; i++) {\n    s = (s * 29 + a) % 7919;\n  }\n  assert(s != 5);\n  return 0;\n"
        ),
        (
            "  int a = __VERIFIER_nondet_int();\n  int s = 1;\n  for (int i = 0; i < 26; i++) {\n    s = (s * 41 + a * a) % 1000003;\n  }\n  assert(s != 11);\n  return 0;\n"
        ),
        (
            "  int a = __VERIFIER_nondet_int();\n  int s = 9;\n  for (int i = 0; i < 24; i++) {\n    s = (s * 53 + a) % 2147483647;\n  }\n  assert(s != 100);\n  return 0;\n"
        ),
    ]
    return [
        Entry(f"deep_{i:03d}", "deep", "timeout", "out-of-subset", _harness(p))
        for i, p in enumerate(bodies)
    ]


def build_corpus() -> tuple[list[Entry], dict[str, object]]:
    entries = [
        *_safe_entries(),
        *_overflow_entries(),
        *_divzero_entries(),
        *_bounds_entries(),
        *_pointer_entries(),
        *_deep_entries(),
    ]
    meta = {
        "esbmc_pin": ESBMC_PIN,
        "release_tag": RELEASE_TAG,
        "generator": "tools/gen_c_corpus.py",
        "families": {
            "safe-assert": 15,
            "overflow": 10,
            "div-zero": 5,
            "bounds": 10,
            "pointer-heap": 5,
            "deep": 5,
        },
        "note": (
            "`expected` is the pinned ESBMC binary's model-checking verdict at "
            "generation time (a run record, never a deductive upgrade); "
            "`import` records what uvil.adapters.esbmc.import_c must do "
            "(obligations in-subset, or an I7 parse diagnostic for "
            "out-of-subset families). deep entries expect a subprocess-budget "
            "timeout (observed: each exceeds 45s under the pin) and are "
            "behind the pytest `slow` marker."
        ),
    }
    return entries, meta


def generate() -> dict[str, object]:
    entries, meta = build_corpus()
    # coherence: every entry must import exactly as the manifest will claim
    for entry in entries:
        result = import_c(entry.source, filename=f"{entry.stem}.c")
        if entry.import_kind == "obligations":
            if not result.ok or not result.obligations:
                raise SystemExit(
                    f"{entry.stem}: manifest says obligations but import gave "
                    f"{len(result.obligations)} obligation(s), diagnostics="
                    f"{[d.native_message for d in result.diagnostics]}"
                )
        elif not result.diagnostics:
            raise SystemExit(f"{entry.stem}: manifest says out-of-subset but import succeeded")

    C_CORPUS.mkdir(parents=True, exist_ok=True)
    current: set[str] = set()
    for entry in entries:
        path = C_CORPUS / f"{entry.stem}.c"
        path.write_bytes(entry.source.encode("utf-8"))
        current.add(path.name)
    for stale in C_CORPUS.glob("*.c"):
        if stale.name not in current:
            stale.unlink()

    expected = {
        e.stem: {
            "file": f"{e.stem}.c",
            "family": e.family,
            "expected": e.expected,
            "import": e.import_kind,
        }
        for e in entries
    }
    return {"meta": meta, "expected": expected}


def main() -> int:
    payload = generate()
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    total = len(payload["expected"])
    print(f"wrote {EXPECTED_PATH}: {total} entries")
    if total < 50:
        raise SystemExit(f"corpus too small: {total} < 50")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
