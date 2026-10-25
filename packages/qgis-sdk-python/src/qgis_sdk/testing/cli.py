"""A ``CliRuntime`` a test owns: in-memory streams, a chosen cwd and env."""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from qgis_sdk.cli import CliRuntime

__all__ = ["FakeCliRuntime", "FakeProcess"]

ExitCodeFor = Callable[[Sequence[str], Path], int]


class FakeProcess:
    """A background process a test can inspect: never runs, remembers being stopped."""

    def __init__(self, argv: Sequence[str], cwd: Path, exit_code: int = 0) -> None:
        self.argv = tuple(argv)
        self.cwd = Path(cwd)
        self.exit_code = exit_code
        self.terminated = False

    def poll(self) -> int | None:
        return self.exit_code if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.terminated = True
        return self.exit_code


class FakeCliRuntime(CliRuntime):
    """Pass to ``CliRunner().invoke(app, args, obj=...)`` and read the streams back.

    ``input`` is what a question would read; ``interactive`` is whether the
    command may ask one at all. Every process a command would run is recorded
    in :attr:`processes` (its environment in :attr:`environments`, same
    order) and answered with exit code ``0`` unless ``run_process`` says
    otherwise; every process it would start in the background is a
    :class:`FakeProcess` in :attr:`started`.
    """

    def __init__(
        self,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        *,
        input: str = "",
        interactive: bool = False,
        run_process: ExitCodeFor | None = None,
    ) -> None:
        self.processes: list[tuple[tuple[str, ...], Path]] = []
        self.environments: list[Mapping[str, str] | None] = []
        self.started: list[FakeProcess] = []
        exit_code = run_process if run_process is not None else _succeed

        def record(
            argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
        ) -> int:
            self.processes.append((tuple(argv), Path(cwd)))
            self.environments.append(None if env is None else dict(env))
            return exit_code(argv, cwd)

        def start(
            argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
        ) -> FakeProcess:
            process = FakeProcess(argv, cwd)
            self.started.append(process)
            self.environments.append(None if env is None else dict(env))
            return process

        super().__init__(
            cwd=Path(cwd),
            env=dict(env or {}),
            out=io.StringIO(),
            err=io.StringIO(),
            inp=io.StringIO(input),
            interactive=interactive,
            run_process=record,
            start_process=start,
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
