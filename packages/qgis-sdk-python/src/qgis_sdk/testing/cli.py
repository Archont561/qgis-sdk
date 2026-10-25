"""A ``CliRuntime`` a test owns: in-memory streams, a chosen cwd and env."""

from __future__ import annotations

import io
from collections.abc import Mapping
from pathlib import Path

from qgis_sdk.cli import CliRuntime

__all__ = ["FakeCliRuntime"]


class FakeCliRuntime(CliRuntime):
    """Pass to ``CliRunner().invoke(app, args, obj=...)`` and read the streams back."""

    def __init__(self, cwd: Path, env: Mapping[str, str] | None = None) -> None:
        super().__init__(
            cwd=Path(cwd),
            env=dict(env or {}),
            out=io.StringIO(),
            err=io.StringIO(),
        )

    @property
    def stdout(self) -> str:
        """Everything the command wrote to ``out`` so far."""
        return self.out.getvalue()  # type: ignore[attr-defined]

    @property
    def stderr(self) -> str:
        """Everything the command wrote to ``err`` so far."""
        return self.err.getvalue()  # type: ignore[attr-defined]
