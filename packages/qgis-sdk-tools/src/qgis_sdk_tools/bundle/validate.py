"""Build-time findings on top of ``check_project``: entry point, dependencies, assets.

Same :class:`Diagnostic` shape as ``check`` so the build prints one list.
(``ENTRY001`` - no ``classFactory`` - retired with decision-43: the build
binds it itself, and ``check`` reports a hand-written one as ``ENTRY002``.)
Rules:

``DEP001``
    A plugin module imports a top-level package that neither the standard
    library, QGIS/Qt, the SDK runtime nor the plugin provides. The ZIP
    cannot carry it, so the plugin would fail on a clean QGIS. The author
    vendors it or declares it under ``[tool.qgis-sdk.build] external`` when
    every target QGIS ships it.
``DEP002``
    A plugin module imports ``qgis_sdk.testing``, which a built plugin never
    gets (decision-35).
``WEB001``
    The project has a web UI but no built page to ship.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Final

from qgis_sdk_tools.check import Diagnostic

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
_CONFIG_TABLE: Final = ("tool", "qgis-sdk", "build")


def external_dependencies(root: Path) -> tuple[tuple[str, ...], list[Diagnostic]]:
    """``[tool.qgis-sdk.build] external``: roots the target QGIS is declared to ship."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return (), []
    relative = Path("pyproject.toml")
    try:
        data: object = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return (), []  # check_project already reported CONFIG001
    for key in _CONFIG_TABLE:
        if not isinstance(data, dict):
            return (), []
        data = data.get(key)
        if data is None:
            return (), []
    if not isinstance(data, dict):
        return (), [_config(relative, "[tool.qgis-sdk.build] must be a table")]
    names = data.get("external", [])
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        return (), [
            _config(
                relative,
                "[tool.qgis-sdk.build] external must be a list of import roots",
            )
        ]
    return tuple(names), []


def check_dependencies(
    root: Path,
    plugin: str,
    files: Sequence[Path],
    *,
    external: Sequence[str] = (),
) -> Iterator[Diagnostic]:
    """``DEP001``/``DEP002`` for imports a clean QGIS would not resolve."""
    allowed = set(sys.stdlib_module_names) | HOST_ROOTS | set(external)
    allowed.update({plugin, "qgis_sdk"})
    for path in files:
        relative = path.relative_to(root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        seen: set[str] = set()
        for node in ast.walk(tree):
            for name, where in _absolute_imports(node):
                head = name.split(".", 1)[0]
                if name == TESTING_PACKAGE or name.startswith(TESTING_PACKAGE + "."):
                    yield Diagnostic(
                        rule="DEP002",
                        path=relative,
                        line=where.lineno,
                        column=where.col_offset + 1,
                        message=f"`{TESTING_PACKAGE}` is not shipped in a built plugin",
                        remediation=(
                            "The fakes are for tests; import them from the project's "
                            "tests only."
                        ),
                    )
                    continue
                if head == TOOLS_PACKAGE:
                    yield Diagnostic(
                        rule="DEP001",
                        path=relative,
                        line=where.lineno,
                        column=where.col_offset + 1,
                        message=(
                            f"`{head}` is the developer tooling and never ships "
                            "in a built plugin"
                        ),
                        remediation=(
                            "A plugin imports the runtime (`qgis_sdk.*`) only; "
                            "move tooling calls to scripts or tests."
                        ),
                    )
                    continue
                if head in allowed or head in seen:
                    continue
                seen.add(head)
                yield Diagnostic(
                    rule="DEP001",
                    path=relative,
                    line=where.lineno,
                    column=where.col_offset + 1,
                    message=(
                        f"`{head}` is imported but neither the standard library, "
                        "QGIS, the SDK runtime nor the plugin provides it"
                    ),
                    remediation=(
                        "Vendor it inside the plugin package, or declare it under "
                        '[tool.qgis-sdk.build] `external = ["' + head + '"]` when '
                        "every QGIS you target ships it."
                    ),
                )


def check_web_assets(assets: Path, plugin: str) -> Iterator[Diagnostic]:
    """``WEB001`` when a web project has no built page under ``<plugin>/web``."""
    if (assets / "index.html").is_file():
        return
    yield Diagnostic(
        rule="WEB001",
        path=Path(plugin) / "web",
        line=0,
        column=0,
        message="the project has a web UI but no built page to ship",
        remediation=(
            "Run the web build (`qgis-sdk build` does it when web/node_modules "
            "exists) or build it yourself before passing --no-web."
        ),
    )


def _absolute_imports(node: ast.AST) -> Iterator[tuple[str, ast.stmt]]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name, node
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        yield node.module, node


def _config(path: Path, message: str) -> Diagnostic:
    return Diagnostic(
        rule="CONFIG001",
        path=path,
        line=0,
        column=0,
        message=message,
        remediation='Write it as `external = ["numpy"]`.',
    )
