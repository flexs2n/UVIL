"""Pinned-version Dafny frontend (subprocess) - the second import path.

`DafnyFrontend.translate` runs the Dafny 4.9.0 legacy CLI
(`dafny /noVerify /compile:0 /print:<file> /pretty:1 <input.dfy>`, which prints
the generated Boogie program - Dafny 4.9 has no `translate boogie` subcommand)
and returns the Boogie text verbatim. `subset_slice` extracts the user
procedures from that text so it feeds the *same* subset parser as direct `.bpl`
input (one parse path, two frontends). The Dafny version must match
`PINNED_DAFNY` exactly (ADR 0002); a present-but-different binary is a hard
failure (I7 `semantic-mismatch` upstream), while an entirely absent binary
raises `DafnyNotInstalled` so callers/tests can skip cleanly.

`subset_slice` is a LOSSY, documented extraction (the downgrade is measured,
never hidden - callers report the dropped-line count): Dafny's Boogie output
embeds its heap/memory-model prelude and per-procedure boilerplate
(`$Heap`, `$FunctionContextHeight`, the `$_ModifiesFrame` lambda, free
requires/ensures) that is outside the accepted subset. The slice keeps only
user `implementation` blocks re-headed as `procedure` with their filtered
contracts and bodies; anything the filter drops would fail the subset parser
loudly anyway if kept verbatim.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Recorded at install time per docs/decisions/0002-tool-pinning.md.
# Install: dotnet tool install --global Dafny --version <PIN>
PINNED_DAFNY = "4.9.0"

# Lines of the printed Boogie program carrying Dafny memory-model boilerplate
# (subset-foreign symbols; user identifiers never contain `$`).
_MODEL_SYMBOLS = (
    "$Heap",
    "$FunctionContextHeight",
    "$_ModifiesFrame",
    "$_reverifyPost",
    "$Unbox",
    "read(",
    "alloc",
    "lambda",
    "forall",
)


class DafnyNotInstalled(Exception):
    pass


class DafnyVersionMismatch(Exception):
    def __init__(self, pinned: str, found: str) -> None:
        super().__init__(
            f"Dafny version mismatch: pinned {pinned!r}, found {found!r} "
            "(see docs/decisions/0002-tool-pinning.md)"
        )
        self.pinned = pinned
        self.found = found


class DafnyTranslateError(Exception):
    def __init__(self, native_message: str) -> None:
        super().__init__(f"dafny translate failed: {native_message}")
        self.native_message = native_message


def parse_dafny_version(version_output: str) -> str:
    """Extract `major.minor.patch` from `dafny --version` output (raises on garbage)."""
    m = re.search(r"(\d+\.\d+\.\d+)", version_output)
    if m is None:
        raise DafnyVersionMismatch(PINNED_DAFNY, version_output.strip() or "<empty>")
    return m.group(1)


def check_dafny_version(version_output: str) -> str:
    version = parse_dafny_version(version_output)
    if version != PINNED_DAFNY:
        raise DafnyVersionMismatch(PINNED_DAFNY, version)
    return version


class DafnyFrontend:
    def __init__(self, executable: str = "dafny") -> None:
        self.executable = executable

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def _run(self, args: list[str], cwd: Path | None = None) -> str:
        proc = subprocess.run(
            [self.executable, *args],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(cwd) if cwd else None,
            check=False,
        )
        if proc.returncode != 0:
            raise DafnyTranslateError(proc.stderr.strip() or proc.stdout.strip())
        return proc.stdout

    def version(self) -> str:
        if not self.available():
            raise DafnyNotInstalled(self.executable)
        return parse_dafny_version(self._run(["--version"]))

    def translate(self, dfy_path: Path) -> str:
        """Dafny source -> verbatim Boogie text (raises DafnyNotInstalled /
        DafnyVersionMismatch / DafnyTranslateError)."""
        if not self.available():
            raise DafnyNotInstalled(self.executable)
        self.version()  # enforces the pin; mismatch raises
        with tempfile.TemporaryDirectory(prefix="uvil-dafny-") as tmp:
            out = Path(tmp) / "printed.bpl"
            proc = subprocess.run(
                [
                    self.executable,
                    "/noVerify",
                    "/compile:0",
                    f"/print:{out}",
                    "/pretty:1",
                    str(dfy_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0 or not out.exists():
                raise DafnyTranslateError(
                    proc.stderr.strip() or proc.stdout.strip() or "no Boogie printed"
                )
            return out.read_text(encoding="utf-8")


def subset_slice(boogie_text: str) -> tuple[str, int]:
    """Extract the user-procedure slice from a printed Dafny Boogie program.

    Returns (sliced_text, dropped_line_count). Deterministic, with two name
    normalizations (documented, injective): Dafny's `#<n>` variable suffixes
    become `_<n>` (`#` is not an SMT-LIB simple-symbol character), and
    implementation headers are re-headed as `procedure` with their qualified
    name mangled to subset-identifier characters. Implementation blocks carry
    the signature/body; contracts travel from the declaration block. Every
    line containing a memory-model symbol (or a `free` modifier, which the
    subset spells differently) is dropped - counted, never silently kept.
    """
    lines = boogie_text.splitlines()
    impl_starts = [i for i, ln in enumerate(lines) if ln.startswith("implementation ")]
    out: list[str] = []
    dropped = 0
    for start in impl_starts:
        # the implementation block: header ... body ... closing brace at col 0
        end = next((i for i in range(start, len(lines)) if lines[i] == "}"), None)
        if end is None:  # pragma: no cover - Dafny always closes the block
            raise DafnyTranslateError("unterminated implementation block in printed Boogie")
        # the declaration block: the last `procedure ` line before this impl
        decl = next((i for i in range(start, -1, -1) if lines[i].startswith("procedure ")), None)
        if decl is None:
            raise DafnyTranslateError("implementation without a procedure declaration")
        out.append(_rehead(lines[start]))
        for ln in lines[decl + 1 : start]:
            if _keep(ln):
                out.append(ln)
            else:
                dropped += 1
        # the block's own `{` line (if any) is kept by _keep below
        for ln in lines[start + 1 : end]:
            if _keep(ln):
                out.append(ln)
            else:
                dropped += 1
        out.append("}")
    sliced = "\n".join(_normalize(ln) for ln in out)
    return sliced, dropped


_HASH_SUFFIX = re.compile(r"#(\d+)")

_HEADER = re.compile(r"^implementation\s+(?P<attrs>(?:\{:[^{}]*\}\s*)*)(?P<name>\S+)\(")


def _rehead(line: str) -> str:
    """`implementation {attrs} Qual.Name(` -> `procedure {attrs} Qual_Name(`."""
    m = _HEADER.match(line)
    if m is None:
        raise DafnyTranslateError(f"unrecognized implementation header: {line!r}")
    mangled = re.sub(r"[^A-Za-z0-9_$']", "_", m.group("name"))
    return f"procedure {m.group('attrs')}{mangled}(" + line[m.end() :]


def _rename_dafny_identifiers(line: str) -> str:
    """Dafny's `#<n>` uniquification suffixes -> `_<n>` (injective rename)."""
    return _HASH_SUFFIX.sub(r"_\1", line)


# `// ----- assignment statement ----- C:\...\vec_push.dfy(8,8)` — the absolute
# source path is machine-local; it is stripped so the slice (and its artifact
# hashes) stay reproducible across machines and pytest tmp_path reuse.
_LOCATION_COMMENT = re.compile(
    r"^(?P<indent>\s*//\s*-----[^-]+-----)\s+\S+\(\d+,\d+\)\s*$"
)


def _normalize(line: str) -> str:
    stripped = _LOCATION_COMMENT.sub(r"\g<indent>", _rename_dafny_identifiers(line))
    return stripped


def _keep(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("//"):
        return True  # blank/comments: parser-skipped, keep for verbatim shape
    if stripped.startswith("free "):
        return False
    return not any(symbol in line for symbol in _MODEL_SYMBOLS)
