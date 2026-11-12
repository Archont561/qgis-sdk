from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.uifile import ui_names

from qgis_sdk_tools.check.diagnostics import Diagnostic

from ._contexts import (
    BINDINGS,
    ICON_DIRECTORY,
    INTERACTIVE_WIDGETS,
    SURFACES,
    UI_MODULES,
    CheckContext,
    UiScope,
    WidgetSite,
    applications,
    collect_imports,
    constructors,
    module_names,
)


class Names:
    """How this module spells ``toolbar``, ``menu``, ``shortcut`` and ``action``."""

    def __init__(self, tree: ast.Module) -> None:
        facts = collect_imports(tree)
        self.bindings = facts.bindings
        self.surfaces = facts.surfaces
        self.on = facts.on
        self.modules = facts.modules
        self.module_names, self.constants = module_names(tree)
        self.applications = applications(tree, constructors(tree), self.modules)

    def _is_module_member(self, node: ast.expr, members: frozenset[str]) -> bool:
        """Whether ``node`` is one of ``members`` on a module this file imported."""
        if not isinstance(node, ast.Attribute) or node.attr not in members:
            return False
        return isinstance(node.value, ast.Name) and node.value.id in self.modules

    def _is_ui_module_member(self, node: ast.expr, members: frozenset[str]) -> bool:
        """Whether ``node`` names a member of the UI package, however it is spelled."""
        if not isinstance(node, ast.Attribute) or node.attr not in members:
            return False
        return isinstance(node.value, ast.Attribute | ast.Name) and (
            ast.unparse(node.value) in UI_MODULES
        )

    def _is_application_action(self, node: ast.expr) -> bool:
        """Whether ``node`` is ``app.action`` for an application this module made."""
        if not isinstance(node, ast.Attribute) or node.attr != "action":
            return False
        return isinstance(node.value, ast.Name) and node.value.id in self.applications

    def is_surface(self, node: ast.ClassDef) -> bool:
        """Whether the class subclasses ``Dialog``/``Dock`` as this module spells them."""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in self.surfaces:
                return True
            if self._is_ui_module_member(base, SURFACES):
                return True
        return False

    def on_target(self, decorator: ast.expr) -> ast.expr | None:
        """The first argument of ``@on(...)`` however the decorator is spelled."""
        call = decorator.value if isinstance(decorator, ast.Attribute) else decorator
        if not isinstance(call, ast.Call) or not call.args:
            return None
        func = call.func
        if isinstance(func, ast.Name):
            return call.args[0] if func.id in self.on else None
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "on"
            and ast.unparse(func.value) in UI_MODULES
        ):
            return call.args[0]
        return None

    def kind(self, decorator: ast.expr) -> str | None:
        """``"toolbar"``/``"menu"``/``"shortcut"``/``"action"`` or ``None``."""
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            if target.id in self.bindings:
                return self.bindings[target.id]
            return None
        if self._is_module_member(target, BINDINGS):
            return target.attr
        if self._is_application_action(target):
            return "action"
        return None


def _input_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """The input names a UI003 message reports, after the context argument."""
    arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    inputs = [argument.arg for argument in arguments][1:]
    if node.args.vararg is not None:
        inputs.append("*" + node.args.vararg.arg)
    if node.args.kwarg is not None:
        inputs.append("**" + node.args.kwarg.arg)
    return inputs


def _ui003(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    bound: list[str],
    inputs: list[str],
    path: Path,
) -> Diagnostic:
    return Diagnostic(
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


def check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, context: CheckContext
) -> Iterator[Diagnostic]:
    kinds = [context.names.kind(decorator) for decorator in node.decorator_list]
    bound = [kind for kind in kinds if kind in BINDINGS]
    if not bound or "action" not in kinds:
        return
    inputs = _input_names(node)
    if not inputs:
        return
    yield _ui003(node, bound, inputs, context.path)


def check_icon(decorator: ast.expr, context: CheckContext) -> Iterator[Diagnostic]:
    if context.names.kind(decorator) != "toolbar" or not isinstance(
        decorator, ast.Call
    ):
        return
    for keyword in decorator.keywords:
        if keyword.arg != "icon" or not isinstance(keyword.value, ast.Constant):
            continue
        icon = keyword.value.value
        if not isinstance(icon, str) or context.package_directory is None:
            continue
        where = context.package_directory / ICON_DIRECTORY / icon
        if Path(icon).name == icon and where.is_file():
            continue
        yield Diagnostic(
            rule="ICON001",
            path=context.path,
            line=keyword.value.lineno,
            column=keyword.value.col_offset + 1,
            message=(
                f"@toolbar icon {icon!r} is not a file under "
                f"{context.package_directory.name}/{ICON_DIRECTORY}/"
            ),
            remediation=(
                f"Add {context.package_directory.name}/{ICON_DIRECTORY}/{icon} to "
                "the package (a file name, not a path), or fix the name; QGIS "
                "loads it at initGui."
            ),
        )


def _widget_holders(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[dict[int, str | None], set[str]]:
    """The assignment holders and setObjectName targets of one surface method."""
    holders: dict[int, str | None] = {}
    named: set[str] = set()
    for statement in ast.walk(method):
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            holders[id(statement.value)] = (
                ast.unparse(target)
                if isinstance(target, ast.Name | ast.Attribute)
                else None
            )
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            holders[id(statement.value)] = ast.unparse(statement.target)
        elif (
            isinstance(statement, ast.Call)
            and isinstance(statement.func, ast.Attribute)
            and statement.func.attr == "setObjectName"
        ):
            named.add(ast.unparse(statement.func.value))
    return holders, named


def _widget_diagnostic(call: ast.Call, site: WidgetSite) -> Diagnostic | None:
    from ._declared import callee_name

    """UI001 for one interactive widget without an objectName, else ``None``."""
    widget = callee_name(call)
    if widget not in INTERACTIVE_WIDGETS:
        return None
    target = site.holders.get(id(call))
    if target is not None and target in site.named:
        return None
    where = f"{site.node.name}.{site.method.name}()"
    subject = f"{target} ({widget})" if target else f"an unassigned {widget}"
    return Diagnostic(
        rule="UI001",
        path=site.path,
        line=call.lineno,
        column=call.col_offset + 1,
        message=f"{subject} in {where} has no objectName",
        remediation=(
            (
                f"Call {target}.setObjectName('...') in {where}"
                if target
                else f"Keep the {widget} in a name and call setObjectName on it"
            )
            + " - agents and tests find widgets by objectName (decision-51); "
            "a qgis_sdk.ui component (Text, Number, Button, Form, ...) names "
            "its widget for you."
        ),
    )


def check_surface_widgets(
    node: ast.ClassDef, context: CheckContext
) -> Iterator[Diagnostic]:
    """Yield UI001 for interactive widgets built in surface methods."""
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        holders, named = _widget_holders(method)
        site = WidgetSite(node, method, context.path, holders, named)
        for call in ast.walk(method):
            if not isinstance(call, ast.Call):
                continue
            diagnostic = _widget_diagnostic(call, site)
            if diagnostic is not None:
                yield diagnostic


def _read_ui_names(file: Path) -> tuple[tuple[str, ...], str | None]:
    """The widget names a Designer file declares, or the reason it cannot be read."""
    try:
        return tuple(ui_names(file)), None
    except QgisSdkUiError as error:
        reason = "does not exist" if not file.is_file() else str(error)
        return (), reason


def _ui_file_error(
    node: ast.ClassDef, ui: str, file: Path, path: Path, reason: str
) -> Diagnostic:
    shown = file if Path(ui).is_absolute() else path.parent / ui
    return Diagnostic(
        rule="UI002",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=f"{node.name}.ui = {ui!r}: {shown.as_posix()} {reason}",
        remediation=(
            f"Save the Designer form next to {path.name} as {ui}, or point "
            "`ui` at the file; the host loads it before wiring @on."
        ),
    )


def _ui_scope(node: ast.ClassDef, context: CheckContext) -> UiScope | None:
    from ._declared import class_constant

    """Read the Designer file once, or record why it cannot be read."""
    ui = class_constant(node, "ui")
    if not isinstance(ui, str) or not ui:
        return None
    file = context.directory / ui  # type: ignore[operator]
    declared, reason = _read_ui_names(file)
    if reason is not None:
        error = _ui_file_error(node, ui, file, context.path, reason)
        return UiScope(node, ui, "", (), context.path, error)
    known = ", ".join(declared) or "none"
    return UiScope(node, ui, known, declared, context.path, None)


def _ui_name_diagnostic(decorator: ast.expr, name: str, scope: UiScope) -> Diagnostic:
    return Diagnostic(
        rule="UI002",
        path=scope.path,
        line=decorator.lineno,
        column=decorator.col_offset + 1,
        message=(
            f"@on({name!r}) in {scope.node.name}: {scope.ui} declares no "
            f"widget named {name!r}"
        ),
        remediation=(
            f"Use one of the objectNames the file declares ({scope.known}) or "
            "name the widget in Qt Designer; wiring fails when the "
            "surface opens otherwise."
        ),
    )


def check_ui_names(node: ast.ClassDef, context: CheckContext) -> Iterator[Diagnostic]:
    from ._declared import literal_name

    """Yield UI002 when ``@on`` names no widget in the Designer file."""
    scope = _ui_scope(node, context)
    if scope is None:
        return
    if scope.error is not None:
        yield scope.error
        return
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in method.decorator_list:
            name = literal_name(context.names.on_target(decorator), context.names)
            if name is None or name in scope.declared:
                continue
            yield _ui_name_diagnostic(decorator, name, scope)


def bound_attributes(node: ast.ClassDef) -> dict[str, ast.expr | None]:
    from ._declared import bound_names

    """The class attributes UI005 can resolve, including bare definitions."""
    bound: dict[str, ast.expr | None] = {}
    for statement in node.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = statement.value
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name):
                bound[statement.target.id] = statement.value
        else:
            for name in bound_names(statement):
                bound.setdefault(name, None)
    return bound
