"""Sort every import a plugin makes into the bucket that decides what ships.

decision-50 point 3: an author learns the bucket of each import at ``check``
time, not from a traceback in a clean QGIS. The buckets are ``stdlib``,
``host`` (QGIS, Qt, ``processing``, ``osgeo``), ``runtime`` (``qgis_sdk``),
``plugin`` (the package itself), ``vendored`` (a declared
``[tool.qgis-sdk.build] vendor`` distribution's import roots), ``external``
(a declared external the target QGIS is assumed to ship) and ``unknown``.

Only ``unknown`` costs anything: it becomes ``DEP001`` - the ZIP cannot carry
it, so the plugin would fail on a clean QGIS - naming both exits (vendor it,
or declare it external). ``qgis_sdk_tools`` is unknown with its own message,
and ``qgis_sdk.testing`` is runtime-but-never-shipped (``DEP002``). Nothing
here imports the project or the distribution; sources are parsed and
distribution metadata is read.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .diagnostics import Diagnostic

__all__ = [
    "BUCKETS",
    "EXTERNAL",
    "HOST",
    "HOST_ROOTS",
    "PLUGIN",
    "RUNTIME",
    "STDLIB",
    "TESTING_PACKAGE",
    "TOOLS_PACKAGE",
    "UNKNOWN",
    "VENDORED",
    "BucketReport",
    "ImportEntry",
    "bucket_imports",
    "import_findings",
]

STDLIB: Final = "stdlib"
HOST: Final = "host"
RUNTIME: Final = "runtime"
PLUGIN: Final = "plugin"
VENDORED: Final = "vendored"
EXTERNAL: Final = "external"
UNKNOWN: Final = "unknown"
BUCKETS: Final = (STDLIB, HOST, RUNTIME, PLUGIN, VENDORED, EXTERNAL, UNKNOWN)

#: Import roots a QGIS Python always has, beyond the standard library.
HOST_ROOTS: Final = frozenset(
    {
        "qgis",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "osgeo",
        "processing",
        "plugins",
        "console",
    }
)
TOOLS_PACKAGE: Final = "qgis_sdk_tools"
TESTING_PACKAGE: Final = "qgis_sdk.testing"


@dataclass(frozen=True, slots=True)
class ImportEntry:
    """One import root, its bucket, and the first place it is imported."""

    root: str
    bucket: str
    path: Path
    line: int
    column: int

    def render(self) -> str:
        """``root  bucket  path:line`` for the human ``check --imports`` listing."""
        return f"{self.root:<24} {self.bucket:<9} {self.path.as_posix()}:{self.line}"

    def to_json(self) -> dict[str, object]:
        return {
            "root": self.root,
            "bucket": self.bucket,
            "path": self.path.as_posix(),
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True, slots=True)
class BucketReport:
    """Every import root of the plugin package, once, in source order."""

    entries: tuple[ImportEntry, ...]

    def roots(self, bucket: str) -> tuple[str, ...]:
        """The roots sorted into ``bucket``."""
        return tuple(entry.root for entry in self.entries if entry.bucket == bucket)

    def counts(self) -> dict[str, int]:
        """How many roots each bucket holds, ``unknown`` included."""
        return {bucket: len(self.roots(bucket)) for bucket in BUCKETS}

    def render(self) -> str:
        """The bucket listing ``check --imports`` prints."""
        return "\n".join(entry.render() for entry in self.entries)

    def to_json(self) -> dict[str, object]:
        return {
            "counts": self.counts(),
            "imports": [entry.to_json() for entry in self.entries],
        }


def _import_entries(root: Path, files: Sequence[Path]):
    """Yield every import with its root-relative file and AST node."""
    for path in files:
        relative = path.relative_to(root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue  # SYNTAX001 already names an unparsable file
        for node, name in _imports(tree):
            yield relative, node, name


@dataclass(frozen=True, slots=True)
class _BucketContext:
    """The resolved plugin and roots every import is bucketed against."""

    plugin: str
    external_roots: set[str]
    vendored_roots: set[str]


def _entry_for(
    entry_root: str,
    context: _BucketContext,
    relative: Path,
    node: ast.AST,
) -> ImportEntry:
    """Build one first-seen import entry with its resolved bucket."""
    return ImportEntry(
        root=entry_root,
        bucket=_bucket(
            entry_root,
            plugin=context.plugin,
            external=context.external_roots,
            vendored=context.vendored_roots,
        ),
        path=relative,
        line=node.lineno,
        column=node.col_offset + 1,
    )


def _tools_finding(entry: ImportEntry) -> Diagnostic:
    return _finding(
        "DEP001",
        entry,
        f"`{TOOLS_PACKAGE}` is the developer tooling and never ships in a built plugin",
        "A plugin imports the runtime (`qgis_sdk.*`) only; move "
        "tooling calls to scripts or tests.",
    )


def _testing_finding(entry: ImportEntry) -> Diagnostic:
    return _finding(
        "DEP002",
        entry,
        f"`{TESTING_PACKAGE}` is not shipped in a built plugin",
        "The fakes are for tests; import them from the project's tests only.",
    )


def _unknown_finding(entry: ImportEntry) -> Diagnostic:
    return _finding(
        "DEP001",
        entry,
        f"`{entry.root}` is imported but neither the standard "
        "library, QGIS, the SDK runtime nor the plugin provides it",
        "Two exits: vendor it - a pure-Python distribution under "
        "`[tool.qgis-sdk.build] vendor` - or declare it under "
        f'`external = ["{entry.root}"]` when every QGIS you target '
        "ships it; the build then probes it at startup.",
    )


def bucket_imports(
    root: Path,
    plugin: str,
    files: Sequence[Path],
    *,
    external: Iterable[str] = (),
    vendored: Iterable[str] = (),
) -> BucketReport:
    """Bucket every import of ``files`` (paths under ``root``), first seen first."""
    context = _BucketContext(plugin, set(external), set(vendored))
    seen: dict[str, ImportEntry] = {}
    for relative, node, name in _import_entries(root, files):
        entry_root = _entry_root(name)
        if entry_root in seen:
            continue
        seen[entry_root] = _entry_for(entry_root, context, relative, node)

    def order(name: str) -> tuple[str, int, str]:
        entry = seen[name]
        return (entry.path.as_posix(), entry.line, name)

    return BucketReport(entries=tuple(seen[name] for name in sorted(seen, key=order)))


def _finding_for(entry: ImportEntry) -> Diagnostic | None:
    """The one finding this entry earns, if any."""
    if entry.root == TOOLS_PACKAGE:
        return _tools_finding(entry)
    if entry.root == TESTING_PACKAGE:
        return _testing_finding(entry)
    if entry.bucket == UNKNOWN:
        return _unknown_finding(entry)
    return None


def import_findings(report: BucketReport) -> tuple[Diagnostic, ...]:
    """``DEP001``/``DEP002`` for the roots a clean QGIS cannot resolve."""
    findings = [
        finding
        for entry in report.entries
        if (finding := _finding_for(entry)) is not None
    ]
    return tuple(findings)


def _finding(
    rule: str, entry: ImportEntry, message: str, remediation: str
) -> Diagnostic:
    return Diagnostic(
        rule=rule,
        path=entry.path,
        line=entry.line,
        column=entry.column,
        message=message,
        remediation=remediation,
    )


def _bucket(root: str, *, plugin: str, external: set[str], vendored: set[str]) -> str:
    """The dependency bucket one import root belongs to, most specific first."""
    if root == TESTING_PACKAGE or root == "qgis_sdk":
        bucket = RUNTIME
    elif root == TOOLS_PACKAGE:
        bucket = UNKNOWN
    elif root in sys.stdlib_module_names:
        bucket = STDLIB
    elif root in HOST_ROOTS:
        bucket = HOST
    elif root in {plugin, "_vendor"}:
        bucket = PLUGIN
    elif root in vendored:
        bucket = VENDORED
    elif root in external:
        bucket = EXTERNAL
    else:
        bucket = UNKNOWN
    return bucket


def _entry_root(name: str) -> str:
    if name == TESTING_PACKAGE or name.startswith(TESTING_PACKAGE + "."):
        return TESTING_PACKAGE
    return name.split(".", 1)[0]


def _imports(tree: ast.AST) -> tuple[tuple[ast.stmt, str], ...]:
    found: list[tuple[ast.stmt, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.append((node, node.module))
    return tuple(found)
