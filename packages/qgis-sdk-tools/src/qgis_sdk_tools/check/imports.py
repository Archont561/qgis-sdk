"""QGIS001 / ARCH001: native imports that execute when a module loads (decision-14).

The question is *when* an import runs, not whether it appears: a statement in
the module body, a class body, a ``try``, a ``with`` or a module-level ``if``
runs when the module is imported, so a pure test or ``describe_plugin`` cannot
import that module without QGIS. A statement inside a function runs when the
function is called, and a statement under ``if TYPE_CHECKING:`` never runs.
Only the source is read; nothing is imported.
"""

from __future__ import annotations

import ast
import fnmatch
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from .diagnostics import Diagnostic

__all__ = ["NATIVE_ADAPTER_PACKAGE", "NATIVE_ROOTS", "check_source", "module_name"]

# Top-level packages that need a QGIS or Qt runtime to import.
NATIVE_ROOTS = frozenset({"qgis", "PyQt5", "PyQt6", "PySide2", "PySide6"})
# The SDK's own PyQGIS-backed adapters: pure code reaches them from inside the
# function that runs in QGIS, never at import time (ARCH001).
NATIVE_ADAPTER_PACKAGE = "qgis_sdk.adapters.qgis"


def module_name(path: Path) -> str:
    """The dotted module a root-relative file path denotes."""
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def is_native_module(name: str, native_modules: Sequence[str]) -> bool:
    """True when ``name`` matches one of the configured native-module globs."""
    return any(
        name == pattern or fnmatch.fnmatchcase(name, pattern)
        for pattern in native_modules
    )


def check_source(
    source: str, *, path: Path, native_modules: Sequence[str] = ()
) -> Iterator[Diagnostic]:
    """Yield the import-time native imports in ``source``, in source order.

    ``path`` is the root-relative path the diagnostics report and the module
    name is derived from; a module declared native is exempt from both rules.
    """
    module = module_name(path)
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        yield Diagnostic(
            rule="SYNTAX001",
            path=path,
            line=error.lineno or 1,
            column=error.offset or 1,
            message=f"cannot parse `{module}`: {error.msg}",
            remediation="Fix the syntax error; check reads the file without importing it.",
        )
        return
    if is_native_module(module, native_modules):
        return
    for node, imported in _import_time_imports(tree):
        for name in imported:
            diagnostic = _classify(name, node, path=path, module=module)
            if diagnostic is not None:
                yield diagnostic
                break  # one finding per statement, however many names it binds


def _classify(
    name: str, node: ast.stmt, *, path: Path, module: str
) -> Diagnostic | None:
    root = name.split(".", 1)[0]
    if root in NATIVE_ROOTS:
        return Diagnostic(
            rule="QGIS001",
            path=path,
            line=node.lineno,
            column=node.col_offset + 1,
            message=(
                f"`{name}` is imported when the module loads, so `{module}` "
                "cannot be imported or inspected without QGIS"
            ),
            remediation=(
                "Move the import inside the function that uses it, put it under "
                "`if TYPE_CHECKING:` when it only types annotations, or declare the "
                "module native under [tool.qgis-sdk.check] native-modules (or "
                "--native) if it must import QGIS at load time."
            ),
        )
    if name == NATIVE_ADAPTER_PACKAGE or name.startswith(NATIVE_ADAPTER_PACKAGE + "."):
        return Diagnostic(
            rule="ARCH001",
            path=path,
            line=node.lineno,
            column=node.col_offset + 1,
            message=(
                f"`{name}` is the SDK's native adapter package and is imported "
                f"when `{module}` loads"
            ),
            remediation=(
                "Build native contexts inside the function that runs in QGIS "
                "(the scaffold's `build_context`), or declare the module native "
                "under [tool.qgis-sdk.check] native-modules."
            ),
        )
    return None


def _import_time_imports(
    tree: ast.AST,
) -> Iterator[tuple[ast.stmt, tuple[str, ...]]]:
    """Walk only the code that runs on import and yield each import statement."""
    for node in _import_time_nodes(tree):
        if isinstance(node, ast.Import):
            yield node, tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            base = node.module or ""
            names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            yield node, tuple(names)


def _import_time_nodes(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue  # runs when called, not when imported
        if isinstance(child, ast.If) and _is_type_checking(child.test):
            yield from _import_time_nodes_in(child.orelse)
            continue
        yield child
        yield from _import_time_nodes(child)


def _import_time_nodes_in(statements: Iterable[ast.stmt]) -> Iterator[ast.AST]:
    for statement in statements:
        yield statement
        yield from _import_time_nodes(statement)


def _is_type_checking(test: ast.expr) -> bool:
    """``TYPE_CHECKING``, ``typing.TYPE_CHECKING`` or ``t.TYPE_CHECKING``."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
