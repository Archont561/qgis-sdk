"""UI003 / ICON001: Desktop bindings that cannot work as written (decision-55).

``UI003``: an ``@action`` that takes inputs is bound to the toolbar, a menu or
a shortcut, and no surface collects those inputs - the host refuses the
trigger by name rather than inventing a dialog, so ``check`` says so first.
``ICON001``: ``@toolbar(icon="...")`` names a file that is not under the
package's ``icons/`` directory, which would fail at ``initGui``.

Only the source is read (decision-8): the decorators are recognised by the
names the module imports from ``qgis_sdk`` (or ``qgis_sdk.bindings``),
aliases included, so a project that spells ``import qgis_sdk as sdk`` is
checked the same way.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from .diagnostics import Diagnostic

__all__ = ["ICON_DIRECTORY", "check_bindings"]

ICON_DIRECTORY = "icons"
_BINDINGS = frozenset({"toolbar", "menu", "shortcut"})
_SOURCES = frozenset({"qgis_sdk", "qgis_sdk.bindings", "qgis_sdk.declarations"})


def check_bindings(
    source: str, *, path: Path, package_directory: Path | None
) -> Iterator[Diagnostic]:
    """Yield the UI003 and ICON001 findings in ``source``, in source order.

    ``path`` is the root-relative path the diagnostics report;
    ``package_directory`` is where ``icons/`` is looked up (``None`` skips
    ICON001, for a file outside any package).
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return  # SYNTAX001 is the import checker's to report
    names = _Names(tree)
    if not names.bindings and names.modules == ():
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _check_function(node, names, path)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for decorator in node.decorator_list:
                yield from _check_icon(decorator, names, path, package_directory)


class _Names:
    """How this module spells ``toolbar``, ``menu``, ``shortcut`` and ``action``."""

    def __init__(self, tree: ast.Module) -> None:
        self.bindings: dict[str, str] = {}
        self.action: set[str] = set()
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in _SOURCES:
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.name in _BINDINGS:
                        self.bindings[local] = alias.name
                    elif alias.name == "action":
                        self.action.add(local)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _SOURCES:
                        modules.append(alias.asname or alias.name)
        self.modules = tuple(modules)

    def kind(self, decorator: ast.expr) -> str | None:
        """``"toolbar"``/``"menu"``/``"shortcut"``/``"action"`` or ``None``."""
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            if target.id in self.bindings:
                return self.bindings[target.id]
            if target.id in self.action:
                return "action"
            return None
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in self.modules
            and target.attr in (*_BINDINGS, "action")
        ):
            return target.attr
        return None


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: _Names, path: Path
) -> Iterator[Diagnostic]:
    kinds = [names.kind(decorator) for decorator in node.decorator_list]
    bound = [kind for kind in kinds if kind in _BINDINGS]
    if not bound or "action" not in kinds:
        return
    inputs = [
        argument.arg
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    ][1:]
    if node.args.vararg is not None:
        inputs.append("*" + node.args.vararg.arg)
    if node.args.kwarg is not None:
        inputs.append("**" + node.args.kwarg.arg)
    if not inputs:
        return
    yield Diagnostic(
        rule="UI003",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"{node.name} is bound to the Desktop (@{', @'.join(dict.fromkeys(bound))}) "
            f"but takes inputs ({', '.join(inputs)}); nothing collects them"
        ),
        remediation=(
            "Move the binding to a Dialog/Dock surface that calls "
            f"self.ctx.actions.{node.name}(...), or drop the inputs; the host "
            "refuses a typed trigger by name and never generates a dialog."
        ),
    )


def _check_icon(
    decorator: ast.expr, names: _Names, path: Path, package_directory: Path | None
) -> Iterator[Diagnostic]:
    if names.kind(decorator) != "toolbar" or not isinstance(decorator, ast.Call):
        return
    for keyword in decorator.keywords:
        if keyword.arg != "icon" or not isinstance(keyword.value, ast.Constant):
            continue
        icon = keyword.value.value
        if not isinstance(icon, str) or package_directory is None:
            continue
        where = package_directory / ICON_DIRECTORY / icon
        if Path(icon).name == icon and where.is_file():
            continue
        yield Diagnostic(
            rule="ICON001",
            path=path,
            line=keyword.value.lineno,
            column=keyword.value.col_offset + 1,
            message=(
                f"@toolbar icon {icon!r} is not a file under "
                f"{package_directory.name}/{ICON_DIRECTORY}/"
            ),
            remediation=(
                f"Add {package_directory.name}/{ICON_DIRECTORY}/{icon} to the package "
                "(a file name, not a path), or fix the name; QGIS loads it at initGui."
            ),
        )
