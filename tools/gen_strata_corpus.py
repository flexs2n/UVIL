"""Deterministic Strata corpus builder (M4).

- `corpora/strata/upstream/*.st` are VERBATIM copies of the pinned Strata
  checkout (repo commit in `meta.provenance`; Apache/MIT licensed, NOTICE
  preserved in the source files). They are committed directly - the generator
  never fetches; it only verifies byte-identity against... nothing (no
  network): the upstream files are static committed fixtures.
- `corpora/strata/generated/*.st` are deterministic in-subset harnesses
  (documented `program Core` subset of uvil.adapters.strata.importer) with
  by-construction z3 verdicts; regeneration is idempotent.

`expected.json` records, per entry, the import shape: procedures, obligation
count, and the I7 diagnostic kinds out-of-subset entries must produce.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.strata.importer import (  # noqa: E402
    PINNED_STRATA_COMMIT,
    PINNED_STRATA_TOOLCHAIN,
    import_strata,
)

STRATA_CORPUS = REPO_ROOT / "corpora" / "strata"
EXPECTED_PATH = STRATA_CORPUS / "expected.json"

UPSTREAM_FILES = (
    "SimpleProc.core.st",
    "CFGSimple.core.st",
    "LoopSimple.core.st",
    "LoopSimple.csimp.st",
    "SafeBvOps.core.st",
    "TypeError.core.st",
)

# (stem, source) - in-subset `program Core` harnesses, one assert each.
GENERATED: list[tuple[str, str]] = [
    (
        "gen_add_comm",
        """program Core;

procedure add_comm(x : int, y : int)
spec {
}
{
  assert [c]: (int.add(x, y) == int.add(y, x));
};
""",
    ),
    (
        "gen_add_id",
        """program Core;

procedure add_id(x : int)
spec {
}
{
  assert [c]: (int.add(x, 0) == x);
};
""",
    ),
    (
        "gen_distrib",
        """program Core;

procedure distrib(x : int, y : int, z : int)
spec {
}
{
  assert [c]: (int.mul(x, int.add(y, z)) == int.add(int.mul(x, y), int.mul(x, z)));
};
""",
    ),
    (
        "gen_assign_forward",
        """program Core;

procedure assign_forward(x : int)
spec {
}
{
  var y : int;
  y := int.add(x, 1);
  assert [c]: (int.ge(y, int.add(x, 1)));
};
""",
    ),
    (
        "gen_refute_double",
        """program Core;

procedure refute_double(x : int)
spec {
}
{
  assert [c]: (int.add(x, x) == int.mul(3, x));
};
""",
    ),
    (
        "gen_refute_bound",
        """program Core;

procedure refute_bound(x : int)
spec {
  requires (int.ge(x, 10));
}
{
  assert [c]: (int.le(x, 5));
};
""",
    ),
]

EXPECTED_UPSTREAM: dict[str, dict[str, object]] = {
    # verbatim artifacts of the pinned checkout; import behavior pinned
    "SimpleProc.core.st": {"procedures": ["Test"], "obligations": 0, "diagnostics": []},
    "CFGSimple.core.st": {"procedures": [], "obligations": 0, "diagnostics": ["parse"]},
    "LoopSimple.core.st": {"procedures": [], "obligations": 0, "diagnostics": ["parse"]},
    "LoopSimple.csimp.st": {"procedures": [], "obligations": 0, "diagnostics": ["parse"]},
    "SafeBvOps.core.st": {
        "procedures": [],
        "obligations": 0,
        "diagnostics": ["semantic-mismatch"],
    },
    "TypeError.core.st": {
        "procedures": [],
        "obligations": 0,
        "diagnostics": ["semantic-mismatch"],
    },
}

EXPECTED_GENERATED: dict[str, dict[str, object]] = {
    "gen_add_comm.st": {"procedures": ["add_comm"], "obligations": 1, "diagnostics": []},
    "gen_add_id.st": {"procedures": ["add_id"], "obligations": 1, "diagnostics": []},
    "gen_distrib.st": {"procedures": ["distrib"], "obligations": 1, "diagnostics": []},
    "gen_assign_forward.st": {
        "procedures": ["assign_forward"],
        "obligations": 1,
        "diagnostics": [],
    },
    "gen_refute_double.st": {
        "procedures": ["refute_double"],
        "obligations": 1,
        "diagnostics": [],
    },
    "gen_refute_bound.st": {
        "procedures": ["refute_bound"],
        "obligations": 1,
        "diagnostics": [],
    },
}


@dataclass(frozen=True)
class Entry:
    rel: str
    source: str
    expected: dict[str, object]


def build_entries() -> list[Entry]:
    entries: list[Entry] = []
    for name in UPSTREAM_FILES:
        path = STRATA_CORPUS / "upstream" / name
        entries.append(
            Entry(
                rel=f"upstream/{name}",
                source=path.read_text(encoding="utf-8"),
                expected=EXPECTED_UPSTREAM[name],
            )
        )
    for stem, source in GENERATED:
        entries.append(
            Entry(
                rel=f"generated/{stem}.st",
                source=source,
                expected=EXPECTED_GENERATED[f"{stem}.st"],
            )
        )
    return entries


def generate() -> dict[str, object]:
    # coherence: every entry must import exactly as the manifest declares
    entries = build_entries()
    for entry in entries:
        result = import_strata(entry.source, filename=entry.rel)
        diagnostics = sorted(d.kind for d in result.diagnostics)
        expected = entry.expected
        assert sorted(result.procedures) == sorted(expected["procedures"]), entry.rel  # type: ignore[union-attr]
        assert len(result.obligations) == expected["obligations"], entry.rel  # type: ignore[union-attr]
        assert diagnostics == sorted(expected["diagnostics"]), (  # type: ignore[union-attr]
            f"{entry.rel}: {diagnostics} != {expected['diagnostics']}"
        )

    # write the generated harnesses (byte-exact, deterministic); upstream
    # fixtures are committed verbatim and never rewritten
    gen_dir = STRATA_CORPUS / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    current: set[str] = set()
    for entry in entries:
        if not entry.rel.startswith("generated/"):
            continue
        path = STRATA_CORPUS / entry.rel
        path.write_bytes(entry.source.encode("utf-8"))
        current.add(path.name)
    for stale in gen_dir.glob("*.st"):
        if stale.name not in current:
            stale.unlink()

    expected = {
        e.rel: {
            "family": "upstream" if e.rel.startswith("upstream/") else "generated",
            **e.expected,
        }
        for e in build_entries()
    }
    meta = {
        "provenance": {
            "repo": "https://github.com/strata-org/Strata",
            "commit": PINNED_STRATA_COMMIT,
            "toolchain": PINNED_STRATA_TOOLCHAIN,
            "license": "Apache-2.0 / MIT (Strata contributors); upstream files copied verbatim",
            "note": (
                "upstream/*.st are verbatim artifacts of the pinned checkout; "
                "generated/*.st are deterministic in-subset harnesses. Strata's "
                "VC generation is NOT UVIL's TCB (vendor-TCB caveat): imported "
                "obligations carry guarantees only from UVIL's own backends."
            ),
        },
        "importer": "uvil.adapters.strata.importer",
        "generated_count": len(GENERATED),
        "upstream_count": len(UPSTREAM_FILES),
    }
    return {"meta": meta, "expected": expected}


def main() -> int:
    payload = generate()
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {EXPECTED_PATH}: {len(payload['expected'])} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
