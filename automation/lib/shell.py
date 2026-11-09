"""Run a command in the checkout and hand back its exit status.

The automation favors plain subprocess calls over hidden magic: every command
this module runs is one a contributor could type, printed before it runs when
``DOIT_VERBOSE`` asks for it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

__all__ = ["ROOT", "pixi", "run"]


def run(command: Sequence[str], *, cwd: Path | None = None) -> int:
    """Run ``command`` from the repository root and return its exit status."""
    executable = shutil.which(command[0])
    if executable is None:
        print(f"automation: {command[0]} is not on PATH", file=sys.stderr)
        return 127
    print(f"automation: {' '.join(command)}", flush=True)
    completed = subprocess.run(list(command), cwd=cwd or ROOT, check=False)
    return completed.returncode


def pixi(environment: str, *arguments: str) -> int:
    """Run a task of the Pixi environment that owns it.

    The environments are the boundary the repository keeps: the Bun side runs in
    ``bun``, the release build in ``build``. A task that needs another
    environment asks Pixi for it rather than reimplementing the command.
    """
    return run(["pixi", "run", "-e", environment, *arguments])
