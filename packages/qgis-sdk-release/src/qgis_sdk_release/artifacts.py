"""Artifact building and checksum helpers.

Subprocess work goes through an injectable runner so tests assert the exact
commands without executing them.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .errors import QgisSdkReleaseError

__all__ = ["Runner", "build_wheel", "checksums", "twine_check", "write_checksums"]

Runner = Callable[[Sequence[str]], None]


def _default_runner(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def build_wheel(
    package_dir: str | Path,
    outdir: str | Path,
    runner: Runner | None = None,
) -> None:
    """Build one wheel with python-build, without build isolation."""
    run = runner or _default_runner
    run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(outdir),
            str(package_dir),
        ]
    )


def twine_check(wheels: Iterable[Path], runner: Runner | None = None) -> None:
    """Validate wheel metadata and readme rendering with twine."""
    run = runner or _default_runner
    paths = [str(wheel) for wheel in wheels]
    if not paths:
        raise QgisSdkReleaseError("twine check needs at least one wheel")
    run(["twine", "check", *paths])


def checksums(paths: Iterable[Path]) -> list[tuple[str, str]]:
    """Return ``(basename, sha256)`` pairs sorted by path."""
    entries: list[tuple[str, str]] = []
    for path in sorted(paths, key=str):
        target = Path(path)
        if not target.is_file():
            raise QgisSdkReleaseError(f"not a file: {target}")
        entries.append((target.name, hashlib.sha256(target.read_bytes()).hexdigest()))
    return entries


def write_checksums(out_path: Path, entries: Iterable[tuple[str, str]]) -> None:
    """Write a ``sha256sum -c`` compatible SHA256SUMS file."""
    lines = "".join(f"{digest}  {name}\n" for name, digest in entries)
    Path(out_path).write_text(lines, encoding="utf-8")
