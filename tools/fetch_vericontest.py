"""VeriContest upstream fetch (M6/ADR 0009, the closed ADR 0007 deferral).

Fetches the pinned HIPREL-Group/VeriContest checkout (benchmark data under
CC BY 4.0; platform-derived problem statements remain under their source
terms - see DATA_LICENSE.md; commit recorded in
`corpora/vericontest/PROVENANCE.json`) and copies a deterministic sample of
task directories VERBATIM into `corpora/vericontest/upstream/`:

- selection rule: the first SAMPLE_COUNT task dirs of `benchmark/leetcode`
  in sorted (stable-id) order - fixed ids, no randomness;
- each task dir is copied whole (description.md, code.rs, code_spec.rs,
  spec.rs, verified.rs, tags).

The full-benchmark subset scan (all 1007 tasks' verified.rs out of the
scalar-contract import subset - Seq/quantifier/loop/struct fragments
everywhere, measured 2026-09-11) is recorded in the provenance document;
the downstream generator (`tools/gen_vericontest_slice.py`) re-runs the
import scan over the COMMITTED copies only (offline, no network).

Re-running this script re-fetches the pinned commit; the corpus discipline
is that the committed copies never change (verbatim upstream text).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

UPSTREAM_URL = "https://github.com/HIPREL-Group/VeriContest"
UPSTREAM_COMMIT = "b9657edf33b68dbd4992b501967730b30883a04e"
UPSTREAM_LICENSE = (
    "CC BY 4.0 (VeriContest-authored benchmark artifacts, DATA_LICENSE.md); "
    "problem statements/platform metadata remain under the LeetCode/Codeforces "
    "source terms"
)

VERICONTEST_DIR = REPO_ROOT / "corpora" / "vericontest"
UPSTREAM_DIR = VERICONTEST_DIR / "upstream"
PROVENANCE_PATH = VERICONTEST_DIR / "PROVENANCE.json"

SAMPLE_COUNT = 100
SAMPLE_FAMILY = "leetcode"
TOTAL_BENCHMARK_TASKS = 1007  # 690 leetcode + 256 codeforces + 61 extended (at the pinned commit)


def _fetch_pinned() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="uvil-vericontest-"))
    subprocess.run(["git", "init", "--quiet", str(tmp)], check=True)
    subprocess.run(["git", "-C", str(tmp), "remote", "add", "origin", UPSTREAM_URL], check=True)
    subprocess.run(
        ["git", "-C", str(tmp), "fetch", "--quiet", "--depth", "1", "origin", UPSTREAM_COMMIT],
        check=True,
    )
    subprocess.run(["git", "-C", str(tmp), "checkout", "--quiet", "FETCH_HEAD"], check=True)
    return tmp


def main() -> int:
    upstream = _fetch_pinned()
    try:
        family = upstream / "benchmark" / SAMPLE_FAMILY
        tasks = sorted(d for d in family.iterdir() if d.is_dir())[:SAMPLE_COUNT]
        if len(tasks) < SAMPLE_COUNT:
            raise SystemExit(f"upstream sample shrank: {len(tasks)} task dirs < {SAMPLE_COUNT}")

        if UPSTREAM_DIR.exists():
            shutil.rmtree(UPSTREAM_DIR)
        UPSTREAM_DIR.mkdir(parents=True)
        for task in tasks:
            shutil.copytree(task, UPSTREAM_DIR / task.name)

        provenance = {
            "upstream_url": UPSTREAM_URL,
            "upstream_commit": UPSTREAM_COMMIT,
            "license": UPSTREAM_LICENSE,
            "fetched_on": "2026-09-11",
            "sample": {
                "family": SAMPLE_FAMILY,
                "selection_rule": (
                    f"first {SAMPLE_COUNT} task dirs of benchmark/{SAMPLE_FAMILY} "
                    "in sorted stable-id order (no randomness)"
                ),
                "sampled": len(tasks),
                "benchmark_total": TOTAL_BENCHMARK_TASKS,
                "note": (
                    "each task dir is copied VERBATIM (description.md, code.rs, "
                    "code_spec.rs, spec.rs, verified.rs, tags); the harvest's "
                    "ground-truth arm runs the pinned Verus on committed "
                    "verified.rs files; the import arm runs "
                    "uvil.adapters.verus.import_verus on the same committed "
                    "bytes - all 1007 upstream verified.rs files are out of "
                    "the scalar-contract import subset (Seq/quantifier/loop/"
                    "struct fragments; scanned at fetch time), so the measured "
                    "downgrade rate IS the headline and the in-subset "
                    "agreement metric is carried by the UVIL-authored "
                    "generated harnesses (corpora/vericontest/generated/, "
                    "the strata-corpus precedent)."
                ),
            },
        }
        PROVENANCE_PATH.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"copied {len(tasks)} task dirs verbatim; wrote {PROVENANCE_PATH}")
        return 0
    finally:
        shutil.rmtree(upstream.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
