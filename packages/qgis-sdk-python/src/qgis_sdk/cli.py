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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

__all__ = ["CliRuntime", "ProcessRunner", "ProcessStarter", "RunningProcess"]


class ProcessRunner(Protocol):
    """Run ``argv`` in ``cwd`` with the user's terminal attached; return the exit code.

    ``env`` replaces the process environment when given. A missing executable
    is exit code ``127``, the shell's convention, so a caller reports it like
    any other failed command instead of catching ``OSError``.
    """

    def __call__(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
    ) -> int: ...


class RunningProcess(Protocol):
    """What a command holds for a process it started and must stop again."""

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class ProcessStarter(Protocol):
    """Start ``argv`` in ``cwd`` and return without waiting; ``None`` when missing."""

    def __call__(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
    ) -> RunningProcess | None: ...


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
    start_process: ProcessStarter

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
            start_process=start_attached,
        )

    def resolve(self, path: Path) -> Path:
        """Resolve a command-line path against the runtime's working directory."""
        return (self.cwd / path).resolve()


def run_attached(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
) -> int:
    """Run a tool with the terminal attached, so its own output reaches the user."""
    try:
        return subprocess.run(
            list(argv), cwd=cwd, env=None if env is None else dict(env), check=False
        ).returncode
    except FileNotFoundError:
        return 127


def start_attached(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
) -> RunningProcess | None:
    """Start a tool in the background with the terminal attached; None if missing."""
    try:
        return subprocess.Popen(
            list(argv), cwd=cwd, env=None if env is None else dict(env)
        )
    except FileNotFoundError:
        return None


def _is_terminal(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False
