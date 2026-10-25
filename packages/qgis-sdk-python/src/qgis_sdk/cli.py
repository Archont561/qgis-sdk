"""The runtime a ``qgis-sdk`` command receives instead of reaching for the process.

A command gets one :class:`CliRuntime` through Typer's ``ctx.obj``
(decision-34): the shell builds it with :meth:`CliRuntime.for_process`, a test
passes :class:`qgis_sdk.testing.FakeCliRuntime` and owns every effect the
command can have. Library functions take the same values as parameters, so a
caller without a shell never goes through Click.

This module imports nothing beyond the standard library on purpose: the
runtime has to be constructible in an interpreter that forbids native modules.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

__all__ = ["CliRuntime", "ProcessRunner"]

ProcessRunner = Callable[[Sequence[str], Path], int]
"""Run ``argv`` in ``cwd`` with the user's terminal attached; return the exit code.

A missing executable is exit code ``127``, the shell's convention, so a caller
reports it like any other failed command instead of catching ``OSError``.
"""


@dataclass(frozen=True)
class CliRuntime:
    """What a command may read from and write to.

    Fields are concrete capabilities, added by the first command that needs
    them; a command reads them by attribute and never falls back to the
    process when one is missing. ``interactive`` says whether a human is at
    the terminal, which is the only licence a command has to ask a question.
    """

    cwd: Path
    env: Mapping[str, str]
    out: TextIO
    err: TextIO
    inp: TextIO
    interactive: bool
    run_process: ProcessRunner

    @classmethod
    def for_process(cls) -> CliRuntime:
        """The real wiring: the only place that reads the process itself."""
        return cls(
            cwd=Path.cwd(),
            env=os.environ,
            out=sys.stdout,
            err=sys.stderr,
            inp=sys.stdin,
            interactive=_is_terminal(sys.stdin) and _is_terminal(sys.stdout),
            run_process=run_attached,
        )

    def resolve(self, path: Path) -> Path:
        """Resolve a command-line path against the runtime's working directory."""
        return (self.cwd / path).resolve()


def run_attached(argv: Sequence[str], cwd: Path) -> int:
    """Run a tool with the terminal attached, so its own output reaches the user."""
    try:
        return subprocess.run(list(argv), cwd=cwd, check=False).returncode
    except FileNotFoundError:
        return 127


def _is_terminal(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False
