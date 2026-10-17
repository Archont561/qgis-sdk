"""Thin git helpers; every call goes through an injectable runner."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

from .commits import LOG_FORMAT

__all__ = ["Runner", "create_tag", "list_tags", "log_commits"]

Runner = Callable[[Sequence[str]], str]


def _default_runner(command: Sequence[str]) -> str:
    result = subprocess.run(list(command), check=True, capture_output=True, text=True)
    return result.stdout


def list_tags(runner: Runner | None = None) -> tuple[str, ...]:
    """List every ``v``-prefixed tag in the repository."""
    run = runner or _default_runner
    out = run(["git", "tag", "--list", "v*"])
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def log_commits(revision_range: str | None = None, runner: Runner | None = None) -> str:
    """Return raw ``git log`` output in the tool's record format."""
    run = runner or _default_runner
    command = ["git", "log", f"--format={LOG_FORMAT}", "--reverse"]
    if revision_range:
        command.append(revision_range)
    return run(command)


def create_tag(
    tag: str,
    message: str,
    push: bool,
    runner: Runner | None = None,
    remote: str = "origin",
) -> None:
    """Create an annotated tag and optionally push it to the remote."""
    run = runner or _default_runner
    run(["git", "tag", "-a", tag, "-m", message])
    if push:
        run(["git", "push", remote, f"refs/tags/{tag}"])
