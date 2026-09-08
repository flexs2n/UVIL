"""Pinned-version Dafny frontend (subprocess) - the second import path.

`DafnyFrontend.translate` runs `dafny translate boogie --no-verify` and returns
Boogie text that feeds the *same* subset parser as direct `.bpl` input (one parse
path, two frontends). The Dafny version must match `PINNED_DAFNY` exactly
(ADR 0002); a present-but-different binary is a hard failure (I7
`semantic-mismatch` upstream), while an entirely absent binary raises
`DafnyNotInstalled` so callers/tests can skip cleanly.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Recorded at install time per docs/decisions/0002-tool-pinning.md.
# Install: dotnet tool install --global Dafny --version <PIN>
PINNED_DAFNY = "4.9.0"


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
        """Dafny source -> Boogie text (raises DafnyNotInstalled / DafnyVersionMismatch)."""
        if not self.available():
            raise DafnyNotInstalled(self.executable)
        self.version()  # enforces the pin; mismatch raises
        return self._run(["translate", "boogie", "--no-verify", str(dfy_path)])
