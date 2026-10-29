"""What an installed distribution contains, read from metadata and never imported.

decision-50 point 2: ``build`` vendors a pure-Python distribution from the
build interpreter's environment, which first means knowing what that
distribution *is* - its import roots, whether any file is a compiled
extension, what it requires, and which files carry its licence. All of that
is on disk in the ``*.dist-info`` directory; nothing here imports the package
or runs its code, so ``check`` can call it too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Final

from qgis_sdk.models import QgisSdkError

__all__ = [
    "COMPILED_SUFFIXES",
    "Distribution",
    "QGisSdkDistributionError",
    "file_path",
    "normalize",
    "read_distribution",
]

#: Suffixes of an extension module: a distribution carrying one cannot be vendored.
COMPILED_SUFFIXES: Final = (".so", ".pyd", ".dylib")
_METADATA_SUFFIXES: Final = ("-info",)
_LICENCE_PREFIXES: Final = ("license", "licence", "copying", "notice", "copyright")
_REQUIRED_NAME: Final = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class QGisSdkDistributionError(QgisSdkError):
    """A declared distribution is not installed in this environment."""


@dataclass(frozen=True, slots=True)
class Distribution:
    """One installed distribution, as the build needs to see it."""

    name: str
    version: str
    roots: tuple[str, ...]
    files: tuple[Path, ...]
    compiled: tuple[Path, ...]
    requires: tuple[str, ...]
    licences: tuple[Path, ...]

    @property
    def is_pure(self) -> bool:
        """True when no file is a compiled extension."""
        return not self.compiled


def file_path(name: str, relative: Path) -> Path:
    """The installed path of one file the distribution lists."""
    return Path(metadata.distribution(name).locate_file(str(relative)))


def normalize(name: str) -> str:
    """PEP 503 normalisation: ``Ruamel.Yaml`` and ``ruamel_yaml`` are one name."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def read_distribution(name: str) -> Distribution:
    """Read the installed ``name``; :class:`QGisSdkDistributionError` if absent."""
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError as error:
        raise QGisSdkDistributionError(
            f"`{name}` is not installed in this environment; `qgis-sdk build` "
            "vendors the copy the build interpreter imports"
        ) from error
    files = tuple(
        Path(str(item))
        for item in (dist.files or ())
        if not item.parts or item.parts[0] != "__pycache__"
    )
    return Distribution(
        name=dist.metadata["Name"] or name,
        version=dist.version,
        roots=_roots(files),
        files=files,
        compiled=tuple(path for path in files if path.suffix in COMPILED_SUFFIXES),
        requires=_required(dist.requires or ()),
        licences=_licences(files),
    )


def _roots(files: tuple[Path, ...]) -> tuple[str, ...]:
    """The import roots the distribution provides, stdlib-style."""
    roots: set[str] = set()
    for path in files:
        if not path.parts:
            continue
        head = path.parts[0]
        if head.endswith(_METADATA_SUFFIXES) or head == "..":
            continue
        if head.endswith(".py"):
            roots.add(head[: -len(".py")])
        elif path.suffix != ".pyc":
            roots.add(head)
    return tuple(sorted(roots))


def _required(requires: tuple[str, ...]) -> tuple[str, ...]:
    """The names behind the metadata's requirement strings, extras excluded."""
    names: list[str] = []
    for requirement in requires:
        head, _, marker = requirement.partition(";")
        if "extra" in marker:
            continue  # an optional dependency of an extra, never installed by default
        match = _REQUIRED_NAME.match(head)
        if match is not None:
            names.append(match.group(1))
    return tuple(dict.fromkeys(names))


def _licences(files: tuple[Path, ...]) -> tuple[Path, ...]:
    """The licence files the distribution ships, wherever it keeps them."""
    return tuple(
        path
        for path in files
        if path.name.lower().startswith(_LICENCE_PREFIXES) and path.suffix != ".py"
    )
