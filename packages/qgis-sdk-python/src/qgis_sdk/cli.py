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
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

__all__ = ["CliRuntime"]


@dataclass(frozen=True)
class CliRuntime:
    """What a command may read from and write to.

    Fields are concrete capabilities, added by the first command that needs
    them; a command reads them by attribute and never falls back to the
    process when one is missing.
    """

    cwd: Path
    env: Mapping[str, str]
    out: TextIO
    err: TextIO

    @classmethod
    def for_process(cls) -> CliRuntime:
        """The real wiring: the only place that reads the process itself."""
        return cls(cwd=Path.cwd(), env=os.environ, out=sys.stdout, err=sys.stderr)

    def resolve(self, path: Path) -> Path:
        """Resolve a command-line path against the runtime's working directory."""
        return (self.cwd / path).resolve()
