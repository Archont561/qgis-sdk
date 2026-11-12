"""Package shape: what a plugin project must carry, and what it must not."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from ..diagnostics import Diagnostic
from ._constants import EXCLUDED_DIRECTORIES

__all__ = ["check_packages"]


def check_packages(root: Path) -> Iterator[Diagnostic]:
    packages = sorted(child for child in root.iterdir() if _is_package(child))
    if not packages:
        yield Diagnostic(
            rule="PROJECT001",
            path=Path(),
            line=0,
            column=0,
            message=f"no plugin package (a directory with __init__.py) under {root}",
            remediation=(
                "Run from the project root `qgis-sdk new` created, or pass its path."
            ),
        )
        return
    for package in packages:
        yield from _check_host_artifacts(root, package)


def _is_package(child: Path) -> bool:
    """Whether a directory under the project root is a package the check reads.

    An excluded directory is one a provider writes, ``tests`` is not shipped,
    and a directory with no ``__init__.py`` is a fixture or a stray folder.
    """
    if not child.is_dir() or child.name in EXCLUDED_DIRECTORIES:
        return False
    return child.name != "tests" and (child / "__init__.py").is_file()


def _check_host_artifacts(root: Path, package: Path) -> Iterator[Diagnostic]:
    """``META001``/``ENTRY002``: files ``build`` and ``dev`` generate, authored by hand."""
    metadata = package / "metadata.txt"
    if metadata.is_file():
        yield _metadata_finding(root, package, metadata)
    init = package / "__init__.py"
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return  # the import rules report the file itself
    bound = _class_factory_binding(tree)
    if bound is not None:
        yield _class_factory_finding(root, init, bound)


def _metadata_finding(root: Path, package: Path, metadata: Path) -> Diagnostic:
    """``META001``: ``build`` and ``dev`` generate metadata.txt themselves."""
    return Diagnostic(
        rule="META001",
        path=metadata.relative_to(root),
        line=0,
        column=0,
        message=(
            f"`{package.name}` carries a hand-written metadata.txt; `build` and "
            "`dev` generate it from pyproject.toml"
        ),
        remediation=(
            "Delete the file. Move `version`, `description` and the author to "
            "[project], `qgisMinimumVersion` to [tool.qgis-sdk] "
            "qgis-minimum-version, and any other key to [tool.qgis-sdk.metadata] "
            "(decision-43)."
        ),
    )


def _class_factory_finding(root: Path, init: Path, bound: ast.AST) -> Diagnostic:
    """``ENTRY002``: ``host()`` binds classFactory, not the author."""
    return Diagnostic(
        rule="ENTRY002",
        path=init.relative_to(root),
        line=bound.lineno,
        column=bound.col_offset + 1,
        message=(
            "__init__.py binds `classFactory`; `build` and `dev` bind it through "
            "`qgis_sdk.adapters.desktop.host()`"
        ),
        remediation=(
            "Delete the definition or import (and the Desktop wrapper it "
            "points at); name the class in `[tool.qgis-sdk] plugin` instead."
        ),
    )


def _class_factory_binding(tree: ast.Module) -> ast.stmt | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == "classFactory":
                return node
        elif isinstance(node, ast.ImportFrom):
            if any((a.asname or a.name) == "classFactory" for a in node.names):
                return node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "classFactory":
                    return node
    return None
