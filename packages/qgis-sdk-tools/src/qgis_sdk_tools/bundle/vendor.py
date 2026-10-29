"""Ship the runtime, and declared packages, under a plugin-private import path.

decision-35 and decision-3: a built ZIP must run in a QGIS that has no
``qgis_sdk`` installed, and two plugins built against different SDK versions
must coexist in one QGIS. So the runtime package is copied into
``<plugin>/_vendor/qgis_sdk`` and every absolute ``qgis_sdk`` import - in
the copy and in the plugin's own sources - is rewritten to
``<plugin>._vendor.qgis_sdk``. The runtime never imports itself by string,
so a textual rewrite of import statements, located through the AST, is
exact. Relative imports inside the runtime are left alone; they already
resolve inside the copy.

decision-50 point 2 reuses exactly that machinery for a declared
``[tool.qgis-sdk.build] vendor`` distribution: a pure-Python distribution is
copied under ``_vendor/`` with its own absolute imports of other vendored
roots rewritten the same way, its licence goes to ``_vendor/LICENSES/``, and
its name and version are recorded in the NOTICE. A distribution carrying a
compiled extension is refused at ``check`` time (``DEP003``), and one of its
requirements that is neither vendored nor external is ``DEP004``. Resolving a
dependency by *string* at runtime (``importlib.import_module("numpy")``) is
outside what a textual rewrite can see; doc-12 says so.
"""

from __future__ import annotations

import ast
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import qgis_sdk

from qgis_sdk_tools.check.versions import installed_runtime_version
from qgis_sdk_tools.distributions import Distribution, file_path, normalize

RUNTIME_PACKAGE: Final = "qgis_sdk"
#: Where a vendored distribution's licence file lands, beside the copies.
LICENCES_DIRECTORY: Final = "LICENSES"
#: Subpackages a built plugin never needs (fakes for tests; see decision-35).
EXCLUDED_SUBPACKAGES: Final = frozenset({"testing"})
EXCLUDED_NAMES: Final = frozenset({"__pycache__"})


def _from_pattern(root: str) -> re.Pattern[str]:
    """``from <root>`` at the start of an import statement, for one root."""
    return re.compile(r"(\bfrom\s+)" + re.escape(root) + r"\b")


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


def rewrite_imports(
    source: str, *, prefix: str, roots: Sequence[str] = (RUNTIME_PACKAGE,)
) -> str:
    """Move every absolute import of ``roots`` in ``source`` under ``prefix``.

    ``prefix`` is the dotted package holding the copies
    (``my_plugin._vendor``); ``roots`` are the import roots that live there -
    the runtime and, for decision-50, each vendored distribution's. Only
    import statements change, found through the AST so strings and comments
    are untouched; the line count is preserved so tracebacks keep their
    numbers. ``import numpy.linalg`` binds the name ``numpy`` in the original,
    so its rewrite imports the submodule and then binds the same name from the
    vendored parent.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            root = _vendored_root(node.module, roots)
            if node.level or root is None:
                continue
            index = node.lineno - 1
            lines[index] = _from_pattern(root).sub(
                rf"\g<1>{prefix}.{root}", lines[index], count=1
            )
        elif isinstance(node, ast.Import):
            moved = [alias for alias in node.names if _vendored_root(alias.name, roots)]
            if not moved:
                continue
            index = node.lineno - 1
            lines[index] = _rewrite_import_line(lines[index], node, roots, prefix)
    return "".join(lines)


def _rewrite_import_line(
    line: str, node: ast.Import, roots: Sequence[str], prefix: str
) -> str:
    newline = line[len(line.rstrip("\r\n")) :]
    indent = line[: len(line) - len(line.lstrip())]
    statements = [_import_statement(alias, roots, prefix) for alias in node.names]
    return indent + "; ".join(statements) + newline


def _import_statement(alias: ast.alias, roots: Sequence[str], prefix: str) -> str:
    root = _vendored_root(alias.name, roots)
    if root is None:
        return (
            f"import {alias.name}"
            if alias.asname is None
            else f"import {alias.name} as {alias.asname}"
        )
    if alias.asname is not None:
        return f"import {prefix}.{alias.name} as {alias.asname}"
    if alias.name == root:
        return f"from {prefix} import {root}"
    return f"import {prefix}.{alias.name}; from {prefix} import {root}"


def _vendored_root(name: str | None, roots: Sequence[str]) -> str | None:
    """Which declared root (if any) an absolute import name belongs to."""
    if name is None:
        return None
    for root in roots:
        if name == root or name.startswith(root + "."):
            return root
    return None


def notice(
    version: str,
    *,
    requirement: str | None = None,
    vendored: Sequence[tuple[str, str]] = (),
) -> str:
    """The NOTICE placed next to the vendored copies.

    ``requirement`` is what the project declared on the runtime; the notice
    records it beside the version that was resolved, so an installed ZIP
    says which runtime it carries and why (decision-43 amendment).
    ``vendored`` adds one ``(name, version)`` line per distribution decision-50
    copied, with where its licence landed, so the ZIP says what it carries.
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
        "https://github.com/Archont561/qgis-sdk\n" + _vendor_section(vendored)
    )


def _vendor_section(vendored: Sequence[tuple[str, str]]) -> str:
    if not vendored:
        return ""
    lines = [
        "",
        "Vendored distributions, copied by `qgis-sdk build` from the build",
        "interpreter's environment (decision-50 point 2):",
        "",
    ]
    for name, version in vendored:
        lines.append(
            f"  {name} {version} - licence under "
            f"{LICENCES_DIRECTORY}/{normalize(name)}-{version}-*"
        )
    return "\n".join(lines) + "\n"


def vendored_roots(distributions: Sequence[Distribution]) -> tuple[str, ...]:
    """Every import root the declared distributions provide, sorted."""
    return tuple(sorted({root for item in distributions for root in item.roots}))


def stage_vendored(
    vendor: Path, distributions: Sequence[Distribution], *, prefix: str
) -> tuple[str, ...]:
    """Copy pure-Python distributions under ``vendor``; return their notices.

    Every ``.py`` file has its own absolute imports of the vendored roots
    rewritten, exactly like the runtime's copy, so ``pandas`` finding
    ``import numpy`` inside itself resolves to this plugin's copy. Files are
    copied byte for byte otherwise (data, ``py.typed``, translations).
    """
    roots = vendored_roots(distributions)
    licences = vendor / LICENCES_DIRECTORY
    records: list[tuple[str, str]] = []
    for distribution in distributions:
        for relative in distribution.files:
            if not relative.parts or relative.parts[0] not in distribution.roots:
                continue
            source = file_path(distribution.name, relative)
            target = vendor / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative.suffix == ".py":
                target.write_text(
                    rewrite_imports(
                        source.read_text(encoding="utf-8"), prefix=prefix, roots=roots
                    ),
                    encoding="utf-8",
                    newline="\n",
                )
            else:
                shutil.copyfile(source, target)
        for relative in distribution.licences:
            licences.mkdir(parents=True, exist_ok=True)
            target = (
                licences
                / f"{normalize(distribution.name)}-{distribution.version}-{relative.name}"
            )
            shutil.copyfile(file_path(distribution.name, relative), target)
        records.append((distribution.name, distribution.version))
    return tuple(records)
