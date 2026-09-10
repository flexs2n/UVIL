"""One-time external-artifact fetch (WI-2, approved 2026-09-10).

Fetches the pinned boogie-org/boogie upstream checkout (MIT; commit recorded
in `corpora/external/PROVENANCE.json`), scans every upstream `Test/**/*.bpl`
through the subset importer, and copies VERBATIM:

- the in-subset files (import cleanly and yield obligations) into
  `corpora/external/upstream/` as `<dir>__<name>.bpl`;
- a deterministic sample of the out-of-subset files (first N sorted paths
  that produce I7 parse diagnostics) into `corpora/external/upstream_out/`
  with the same naming - their loud outcome is part of the corpus.

The full-scan downgrade numbers (files scanned / importable) are recorded in
the provenance document; the downstream generator (`tools/gen_external_slice.py`)
re-runs the scan over the COMMITTED copies only (offline, no network).

Re-running this script re-fetches the pinned commit; the corpus discipline is
that the committed copies never change (verbatim upstream text).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import import_module  # noqa: E402

UPSTREAM_URL = "https://github.com/boogie-org/boogie"
UPSTREAM_COMMIT = "bb44ad35387110bf4223b20f240ef6150f069842"
UPSTREAM_LICENSE = "MIT (LICENSE.txt: Copyright (c) Microsoft Corporation)"

EXTERNAL_DIR = REPO_ROOT / "corpora" / "external"
UPSTREAM_DIR = EXTERNAL_DIR / "upstream"
OUT_SAMPLE_DIR = EXTERNAL_DIR / "upstream_out"
PROVENANCE_PATH = EXTERNAL_DIR / "PROVENANCE.json"

OUT_SAMPLE_COUNT = 10


def _fetch_pinned() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="uvil-external-"))
    subprocess.run(["git", "init", "--quiet", str(tmp)], check=True)
    subprocess.run(["git", "-C", str(tmp), "remote", "add", "origin", UPSTREAM_URL], check=True)
    subprocess.run(
        ["git", "-C", str(tmp), "fetch", "--quiet", "--depth", "1", "origin", UPSTREAM_COMMIT],
        check=True,
    )
    subprocess.run(["git", "-C", str(tmp), "checkout", "--quiet", "FETCH_HEAD"], check=True)
    return tmp


def _corpus_name(rel: Path) -> str:
    return f"{rel.parent.name}__{rel.name}"


def main() -> int:
    upstream = _fetch_pinned()
    try:
        scanned = 0
        in_subset: list[tuple[Path, Path]] = []
        out_of_subset: list[tuple[Path, int]] = []
        for path in sorted(upstream.joinpath("Test").rglob("*.bpl")):
            rel = path.relative_to(upstream.joinpath("Test"))
            try:
                source = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            try:
                result = import_module(source, path.name)
            except Exception:
                result = None
            if result is not None and result.ok and result.obligations:
                in_subset.append((path, rel))
            elif result is not None and result.diagnostics:
                out_of_subset.append((path, rel))

        UPSTREAM_DIR.mkdir(parents=True, exist_ok=True)
        OUT_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        for stale in UPSTREAM_DIR.glob("*.bpl"):
            stale.unlink()
        for stale in OUT_SAMPLE_DIR.glob("*.bpl"):
            stale.unlink()
        for path, rel in in_subset:
            shutil.copyfile(path, UPSTREAM_DIR / _corpus_name(rel))
        for path, rel in out_of_subset[:OUT_SAMPLE_COUNT]:
            shutil.copyfile(path, OUT_SAMPLE_DIR / _corpus_name(rel))

        provenance = {
            "upstream_url": UPSTREAM_URL,
            "upstream_commit": UPSTREAM_COMMIT,
            "license": UPSTREAM_LICENSE,
            "fetched_on": "2026-09-10",
            "scan": {
                "root": "Test/**/*.bpl",
                "files_scanned": scanned,
                "in_subset_files": len(in_subset),
                "in_subset_obligations": "recorded per file in expected.json",
                "out_of_subset_files": len(out_of_subset),
                "out_of_subset_sample": min(OUT_SAMPLE_COUNT, len(out_of_subset)),
                "note": (
                    "the in-subset selection is the importer's honest outcome over "
                    "the full upstream test set - every file that imports cleanly "
                    "and yields obligations is committed verbatim; the out-of-"
                    "subset downgrade is measured, not hidden, and its first "
                    "sorted sample is committed with pinned loud outcomes."
                ),
            },
        }
        PROVENANCE_PATH.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"scanned {scanned} upstream files: {len(in_subset)} in-subset copied, "
            f"{len(out_of_subset)} out-of-subset (sampled "
            f"{min(OUT_SAMPLE_COUNT, len(out_of_subset))})"
        )
        return 0
    finally:
        shutil.rmtree(upstream.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
