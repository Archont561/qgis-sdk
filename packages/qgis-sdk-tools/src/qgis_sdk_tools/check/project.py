"""``check_project``: walk one plugin project and report, mutating nothing.

Decision-8 fixes the boundaries: no imports of the project, no installs, no
handler execution, no rewrites. ``build`` reuses this function rather than
shelling out to the command.

Rules owned here: ``PROJECT001`` (no package), ``META001`` (a hand-written
``metadata.txt``; ``build``/``dev`` generate it), ``ENTRY002`` (a
hand-written ``classFactory``; ``host()`` binds it), ``CONFIG001`` for
``[tool.qgis-sdk.check]``. The ``pyproject.toml`` rules live in
:mod:`qgis_sdk_tools.project`, the version rules in :mod:`.versions`, the
native UI rules (``UI001``, ``UI003``, ``ICON001``) in :mod:`.ui`.
"""

from __future__ import annotations

import ast
import os
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path

from .diagnostics import CheckReport, Diagnostic, QgisSdkCheckError
from .imports import check_source
from .ui import check_bindings
from .versions import (
    check_generated_clients,
    check_runtime_pins,
    check_runtime_requirement,
)

__all__ = ["EXCLUDED_DIRECTORIES", "REQUIRED_METADATA_KEYS", "check_project"]

# Tooling and dependency trees are never the author's plugin code.
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".venv",
        "venv",
        "node_modules",
        ".pixi",
        "__pycache__",
        "build",
        "dist",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)
# QGIS refuses to load a plugin whose metadata.txt lacks any of these; ``build``
# and ``dev`` render them all from pyproject.toml (``qgis_sdk_tools.project``).
REQUIRED_METADATA_KEYS = (
    "name",
    "description",
    "about",
    "version",
    "qgisMinimumVersion",
    "author",
    "email",
)
_CONFIG_TABLE = ("tool", "qgis-sdk", "check")


def check_project(root: Path, *, native_modules: Sequence[str] = ()) -> CheckReport:
    """Check the project at ``root`` and return every finding.

    ``native_modules`` adds to the globs configured under
    ``[tool.qgis-sdk.check] native-modules`` in the project's ``pyproject.toml``.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise QgisSdkCheckError(
            f"{root} is not a directory; give a plugin project root"
        )
    diagnostics: list[Diagnostic] = []
    configured, config_diagnostics = _configured_native_modules(root)
    diagnostics.extend(config_diagnostics)
    native = (*configured, *native_modules)

    packages = list(_check_packages(root))
    diagnostics.extend(packages)
    if not any(d.rule == "PROJECT001" for d in packages):
        # The plugin class, the metadata.txt values and the page (decision-43).
        from qgis_sdk_tools.project import load_project

        diagnostics.extend(load_project(root)[1])
    # What the project pins against what this release supports (decision-35),
    # and whether the runtime this interpreter would ship is one it declares.
    diagnostics.extend(check_runtime_pins(root))
    diagnostics.extend(check_runtime_requirement(root))
    diagnostics.extend(check_generated_clients(root))

    files = 0
    for path in _python_files(root):
        files += 1
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        diagnostics.extend(check_source(source, path=relative, native_modules=native))
        package = root / relative.parts[0] if len(relative.parts) > 1 else None
        diagnostics.extend(
            check_bindings(source, path=relative, package_directory=package)
        )

    diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))
    return CheckReport(root=root, diagnostics=tuple(diagnostics), files_checked=files)


def _python_files(root: Path) -> Iterator[Path]:
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRECTORIES)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(directory) / filename


def _check_packages(root: Path) -> Iterator[Diagnostic]:
    packages = sorted(
        child
        for child in root.iterdir()
        if child.is_dir()
        and child.name not in EXCLUDED_DIRECTORIES
        and child.name != "tests"
        and (child / "__init__.py").is_file()
    )
    if not packages:
        yield Diagnostic(
            rule="PROJECT001",
            path=Path("."),
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


def _check_host_artifacts(root: Path, package: Path) -> Iterator[Diagnostic]:
    """``META001``/``ENTRY002``: files ``build`` and ``dev`` generate, authored by hand."""
    metadata = package / "metadata.txt"
    if metadata.is_file():
        yield Diagnostic(
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
    init = package / "__init__.py"
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return  # the import rules report the file itself
    bound = _class_factory_binding(tree)
    if bound is not None:
        yield Diagnostic(
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


def _configured_native_modules(root: Path) -> tuple[tuple[str, ...], list[Diagnostic]]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return (), []
    relative = Path("pyproject.toml")
    try:
        data: object = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return (), [
            _config_diagnostic(relative, f"pyproject.toml does not parse: {error}")
        ]
    for key in _CONFIG_TABLE:
        if not isinstance(data, dict):
            return (), []
        data = data.get(key)
        if data is None:
            return (), []
    if not isinstance(data, dict):
        return (), [
            _config_diagnostic(relative, "[tool.qgis-sdk.check] must be a table")
        ]
    globs = data.get("native-modules", [])
    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
        return (), [
            _config_diagnostic(
                relative,
                "[tool.qgis-sdk.check] native-modules must be a list of module globs",
            )
        ]
    return tuple(globs), []


def _config_diagnostic(path: Path, message: str) -> Diagnostic:
    return Diagnostic(
        rule="CONFIG001",
        path=path,
        line=0,
        column=0,
        message=message,
        remediation=(
            'Write it as `native-modules = ["my_plugin.native", "my_plugin.views.*"]`.'
        ),
    )
