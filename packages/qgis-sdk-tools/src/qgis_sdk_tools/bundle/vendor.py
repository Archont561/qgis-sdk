"""Ship the runtime inside the plugin under a plugin-private import path.

decision-35 and decision-3: a built ZIP must run in a QGIS that has no
``qgis_sdk`` installed, and two plugins built against different SDK versions
must coexist in one QGIS. So the runtime package is copied into
``<plugin>/_vendor/qgis_sdk`` and every absolute ``qgis_sdk`` import - in
the copy and in the plugin's own sources - is rewritten to
``<plugin>._vendor.qgis_sdk``. The runtime never imports itself by string,
so a textual rewrite of import statements, located through the AST, is
exact. Relative imports inside the runtime are left alone; they already
resolve inside the copy.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import qgis_sdk

from qgis_sdk_tools.check.versions import installed_runtime_version

RUNTIME_PACKAGE: Final = "qgis_sdk"
#: Subpackages a built plugin never needs (fakes for tests; see decision-35).
EXCLUDED_SUBPACKAGES: Final = frozenset({"testing"})
EXCLUDED_NAMES: Final = frozenset({"__pycache__"})

_IMPORT_PREFIX = re.compile(r"(\bimport\s+)" + RUNTIME_PACKAGE + r"\b")
_FROM_PREFIX = re.compile(r"(\bfrom\s+)" + RUNTIME_PACKAGE + r"\b")


def runtime_source() -> Path:
    """The installed ``qgis_sdk`` package directory to copy from."""
    return Path(qgis_sdk.__file__).resolve().parent


def runtime_version() -> str:
    """The runtime's version - distribution or checkout manifest - or ``unknown``."""
    return installed_runtime_version() or "unknown"


def runtime_files() -> list[Path]:
    """Every file of the runtime to ship, relative to :func:`runtime_source`."""
    source = runtime_source()
    files: list[Path] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.parts[0] in EXCLUDED_SUBPACKAGES:
            continue
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        files.append(relative)
    return files


def rewrite_imports(source: str, *, prefix: str) -> str:
    """Move every absolute ``qgis_sdk`` import in ``source`` under ``prefix``.

    ``prefix`` is the dotted package holding the copy (``my_plugin._vendor``).
    Only import statements change, found through the AST so strings and
    comments are untouched; the line count is preserved so tracebacks keep
    their numbers. ``import qgis_sdk.x`` binds the name ``qgis_sdk`` in the
    original, so its rewrite imports the submodule and then binds the same
    name from the vendored parent.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not _is_runtime(node.module):
                continue
            index = node.lineno - 1
            lines[index] = _FROM_PREFIX.sub(
                rf"\g<1>{prefix}.{RUNTIME_PACKAGE}", lines[index], count=1
            )
        elif isinstance(node, ast.Import):
            runtime_aliases = [a for a in node.names if _is_runtime(a.name)]
            if not runtime_aliases:
                continue
            index = node.lineno - 1
            lines[index] = _rewrite_import_line(
                lines[index], node, runtime_aliases, prefix
            )
    return "".join(lines)


def _rewrite_import_line(
    line: str, node: ast.Import, aliases: list[ast.alias], prefix: str
) -> str:
    newline = line[len(line.rstrip("\r\n")) :]
    indent = line[: len(line) - len(line.lstrip())]
    statements = [_import_statement(alias, prefix) for alias in node.names]
    return indent + "; ".join(statements) + newline


def _import_statement(alias: ast.alias, prefix: str) -> str:
    if not _is_runtime(alias.name):
        return (
            f"import {alias.name}"
            if alias.asname is None
            else f"import {alias.name} as {alias.asname}"
        )
    if alias.asname is not None:
        return f"import {prefix}.{alias.name} as {alias.asname}"
    if alias.name == RUNTIME_PACKAGE:
        return f"from {prefix} import {RUNTIME_PACKAGE}"
    return f"import {prefix}.{alias.name}; from {prefix} import {RUNTIME_PACKAGE}"


def _is_runtime(name: str | None) -> bool:
    return name is not None and (
        name == RUNTIME_PACKAGE or name.startswith(RUNTIME_PACKAGE + ".")
    )


def notice(version: str, *, requirement: str | None = None) -> str:
    """The NOTICE placed next to the vendored copy.

    ``requirement`` is what the project declared on the runtime; the notice
    records it beside the version that was resolved, so an installed ZIP
    says which runtime it carries and why (decision-43 amendment).
    """
    declared = (
        f"The project declared `{requirement}`; "
        if requirement is not None
        else "The project declared no runtime requirement; "
    )
    return (
        f"This directory contains qgis-sdk runtime {version}, copied by\n"
        "`qgis-sdk build` under a plugin-private import path so the plugin runs\n"
        "in a QGIS without qgis-sdk installed and coexists with plugins built\n"
        "against other versions.\n\n"
        f"{declared}the copy is the runtime the build's interpreter imported.\n\n"
        "qgis-sdk is licensed under the MIT License;\n"
        "https://github.com/Archont561/qgis-sdk\n"
    )
