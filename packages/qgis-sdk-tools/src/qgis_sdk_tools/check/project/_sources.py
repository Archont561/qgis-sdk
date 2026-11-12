"""Read every Python file once and report what the source rules find."""

from __future__ import annotations

from pathlib import Path

from ..diagnostics import Diagnostic
from ..hosts import check_hosts
from ..imports import check_source
from ..jobs import check_jobs
from ..ui import check_bindings
from ._vendor import python_files

__all__ = ["source_diagnostics"]


def source_diagnostics(
    root: Path,
    diagnostics: list[Diagnostic],
    native: tuple[str, ...],
    declared_hosts: tuple[str, ...] | None,
) -> int:
    """Read every Python file once and return how many were checked."""
    files = 0
    for path in python_files(root):
        files += 1
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        diagnostics.extend(check_source(source, path=relative, native_modules=native))
        diagnostics.extend(check_jobs(source, path=relative))
        if declared_hosts is not None:
            diagnostics.extend(check_hosts(source, path=relative, hosts=declared_hosts))
        package = root / relative.parts[0] if len(relative.parts) > 1 else None
        diagnostics.extend(
            check_bindings(
                source,
                path=relative,
                package_directory=package,
                directory=path.parent,
            )
        )
    return files
