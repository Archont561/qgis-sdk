"""Read every Python file once and report what the source rules find."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..api import Marks, check_deprecated_usage, deprecated_names
from ..diagnostics import Diagnostic
from ..hosts import check_hosts
from ..imports import check_source
from ..jobs import check_jobs
from ..ui import check_bindings
from ._vendor import python_files

__all__ = ["source_diagnostics"]


@dataclass(frozen=True, slots=True)
class _Sources:
    """What every per-file rule needs to know about the project (decision-81)."""

    root: Path
    native: tuple[str, ...]
    declared_hosts: tuple[str, ...] | None
    deprecations: Marks


def _file_diagnostics(path: Path, sources: _Sources) -> list[Diagnostic]:
    """Every rule that reads one file's text, for that one file."""
    relative = path.relative_to(sources.root)
    source = path.read_text(encoding="utf-8")
    found = list(check_source(source, path=relative, native_modules=sources.native))
    found.extend(check_jobs(source, path=relative))
    found.extend(
        check_deprecated_usage(source, path=relative, deprecations=sources.deprecations)
    )
    if sources.declared_hosts is not None:
        found.extend(check_hosts(source, path=relative, hosts=sources.declared_hosts))
    found.extend(
        check_bindings(
            source,
            path=relative,
            package_directory=_package(path, relative),
            directory=path.parent,
        )
    )
    return found


def _package(path: Path, relative: Path) -> Path | None:
    """The project's top-level package directory, when the file is inside one."""
    return path.parents[len(relative.parts) - 2] if len(relative.parts) > 1 else None


def source_diagnostics(
    root: Path,
    diagnostics: list[Diagnostic],
    native: tuple[str, ...],
    declared_hosts: tuple[str, ...] | None,
    deprecations: Marks | None = None,
) -> int:
    """Read every Python file once and return how many were checked."""
    marks = deprecated_names() if deprecations is None else deprecations
    sources = _Sources(root, native, declared_hosts, marks)
    files = 0
    for path in python_files(root):
        files += 1
        diagnostics.extend(_file_diagnostics(path, sources))
    return files
