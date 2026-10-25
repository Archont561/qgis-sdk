"""A ``CliRuntime`` a test owns: in-memory streams, a chosen cwd and env."""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from pathlib import Path

from qgis_sdk.cli import CliRuntime, ProcessRunner

__all__ = ["FakeCliRuntime"]


class FakeCliRuntime(CliRuntime):
    """Pass to ``CliRunner().invoke(app, args, obj=...)`` and read the streams back.

    ``input`` is what a question would read; ``interactive`` is whether the
    command may ask one at all. Every process a command would spawn is
    recorded in :attr:`processes` and answered with exit code ``0`` unless
    ``run_process`` says otherwise.
    """

    def __init__(
        self,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        *,
        input: str = "",
        interactive: bool = False,
        run_process: ProcessRunner | None = None,
    ) -> None:
        self.processes: list[tuple[tuple[str, ...], Path]] = []
        exit_code = run_process if run_process is not None else _succeed

        def record(argv: Sequence[str], cwd: Path) -> int:
            self.processes.append((tuple(argv), Path(cwd)))
            return exit_code(argv, cwd)

        super().__init__(
            cwd=Path(cwd),
            env=dict(env or {}),
            out=io.StringIO(),
            err=io.StringIO(),
            inp=io.StringIO(input),
            interactive=interactive,
            run_process=record,
        )

    @property
    def stdout(self) -> str:
        """Everything the command wrote to ``out`` so far."""
        return self.out.getvalue()  # type: ignore[attr-defined]

    @property
    def stderr(self) -> str:
        """Everything the command wrote to ``err`` so far."""
        return self.err.getvalue()  # type: ignore[attr-defined]


def _succeed(argv: Sequence[str], cwd: Path) -> int:
    return 0
