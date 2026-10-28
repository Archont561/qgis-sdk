"""UI001 / UI002 / UI003 / UI005 / ICON001: native UI that cannot work as written.

Decision-55 point 7. ``UI001``: a ``Dialog``/``Dock`` method constructs an
interactive Qt or QGIS widget and never calls ``setObjectName`` on it - the
UI snapshots agents read and the tests that drive a window find widgets by
``objectName`` (decision-51), so an unnamed input is invisible to both. The
catalogue's components name their widgets (``form/<field>``,
``buttons/<name>``); hand placed widgets must say their name themselves.
``UI002``: a surface points at a Designer file (``ui = "x.ui"``) and an
``@on(name)`` names a widget the file does not declare, or the file is not
there - the host would refuse the surface when it opens.
``UI003``: an ``@action`` that takes inputs is bound to the toolbar, a menu or
a shortcut, and no surface collects those inputs - the host refuses the
trigger by name rather than inventing a dialog, so ``check`` says so first.
``UI005``: the declarative form read statically - ``@on(attribute)`` names a
class attribute that is a string or a number rather than a component, or a
name the class never binds, and a ``Custom`` declared on the class holds a
widget built when the class is defined (``Custom(widget=QLabel(...))``),
which cannot be copied for each window; the host refuses both when the
surface opens, ``check`` says so first.
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

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.uifile import ui_names

from .diagnostics import Diagnostic

__all__ = ["ICON_DIRECTORY", "INTERACTIVE_WIDGETS", "check_bindings"]

ICON_DIRECTORY = "icons"
_BINDINGS = frozenset({"toolbar", "menu", "shortcut"})
_SOURCES = frozenset({"qgis_sdk", "qgis_sdk.bindings", "qgis_sdk.declarations"})
_SURFACE_SOURCES = frozenset({"qgis_sdk.ui", "qgis_sdk.ui.surfaces"})
_WIRING_SOURCES = frozenset({"qgis_sdk.ui", "qgis_sdk.ui.wiring"})
_UI_MODULES = frozenset({"qgis_sdk.ui", "ui"})
_SURFACES = frozenset({"Dialog", "Dock"})

#: Widget classes a user interacts with; a label or a layout needs no name.
INTERACTIVE_WIDGETS = frozenset(
    {
        # Qt
        "QPushButton",
        "QToolButton",
        "QRadioButton",
        "QCheckBox",
        "QLineEdit",
        "QTextEdit",
        "QPlainTextEdit",
        "QSpinBox",
        "QDoubleSpinBox",
        "QComboBox",
        "QFontComboBox",
        "QSlider",
        "QDial",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QKeySequenceEdit",
        "QListWidget",
        "QTreeWidget",
        "QTableWidget",
        "QListView",
        "QTreeView",
        "QTableView",
        "QTabWidget",
        "QDialogButtonBox",
        # QGIS
        "QgsMapLayerComboBox",
        "QgsFieldComboBox",
        "QgsFieldExpressionWidget",
        "QgsProjectionSelectionWidget",
        "QgsFileWidget",
        "QgsColorButton",
        "QgsSpinBox",
        "QgsDoubleSpinBox",
        "QgsFilterLineEdit",
        "QgsCheckableComboBox",
        "QgsDateTimeEdit",
        "QgsFeatureListComboBox",
        "QgsFeaturePickerWidget",
        "QgsOpacityWidget",
        "QgsScaleWidget",
        "QgsExtentWidget",
        "QgsSymbolButton",
        "QgsFontButton",
        "QgsUnitSelectionWidget",
        "QgsRasterBandComboBox",
        "QgsLayoutComboBox",
    }
)


def check_bindings(
    source: str,
    *,
    path: Path,
    package_directory: Path | None,
    directory: Path | None = None,
) -> Iterator[Diagnostic]:
    """Yield the UI001-UI003 and ICON001 findings in ``source``, in source order.

    ``path`` is the root-relative path the diagnostics report;
    ``package_directory`` is where ``icons/`` is looked up (``None`` skips
    ICON001, for a file outside any package); ``directory`` is where the
    file lives, so a relative ``ui = "x.ui"`` resolves (``None`` skips UI002).
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return  # SYNTAX001 is the import checker's to report
    names = _Names(tree)
    if directory is not None and package_directory is not None:
        names.applications.update(
            _imported_applications(tree, directory, package_directory)
        )
    if not names.bindings and names.modules == () and not names.surfaces:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _check_function(node, names, path)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for decorator in node.decorator_list:
                yield from _check_icon(decorator, names, path, package_directory)
        if isinstance(node, ast.ClassDef) and names.is_surface(node):
            yield from _check_surface_widgets(node, path)
            if directory is not None:
                yield from _check_ui_names(node, names, path, directory)
            yield from _check_declared(node, names, path)


def _imported_applications(
    tree: ast.Module, directory: Path, package_directory: Path
) -> set[str]:
    """Find directly imported local plugins without importing project code."""
    found: set[str] = set()
    package = package_directory.resolve()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.level:
            base = directory
            for _ in range(node.level - 1):
                base = base.parent
            parts = node.module.split(".")
        else:
            parts = node.module.split(".")
            if parts[0] != package.name:
                continue
            base = package
            parts = parts[1:]
        module = base.joinpath(*parts)
        candidates = (module.with_suffix(".py"), module / "__init__.py")
        for candidate in candidates:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(package) or not resolved.is_file():
                continue
            try:
                imported = ast.parse(resolved.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, SyntaxError):
                break
            applications = _Names(imported).applications
            found.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in applications
            )
            break
    return found


class _Names:
    """How this module spells ``toolbar``, ``menu``, ``shortcut`` and ``action``."""

    def __init__(self, tree: ast.Module) -> None:
        self.bindings: dict[str, str] = {}
        self.surfaces: set[str] = set()
        self.on: set[str] = set()
        #: Module-level ``NAME = "literal"`` assignments, for ``@on(NAME)``.
        self.constants: dict[str, str] = {}
        #: Every name the module binds at top level (imports, defs, assignments).
        self.module_names: set[str] = set()
        for statement in tree.body:
            self.module_names.update(_bound_names(statement))
            if (
                isinstance(statement, ast.Assign)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        self.constants[target.id] = statement.value.value
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (
                _SURFACE_SOURCES | _WIRING_SOURCES
            ):
                for alias in node.names:
                    if alias.name in _SURFACES and node.module in _SURFACE_SOURCES:
                        self.surfaces.add(alias.asname or alias.name)
                    elif alias.name == "on" and node.module in _WIRING_SOURCES:
                        self.on.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module in _SOURCES:
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.name in _BINDINGS:
                        self.bindings[local] = alias.name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _SOURCES:
                        modules.append(alias.asname or alias.name)
        self.modules = tuple(modules)
        constructors = {
            alias.asname or alias.name
            for statement in tree.body
            if isinstance(statement, ast.ImportFrom) and statement.module == "qgis_sdk"
            for alias in statement.names
            if alias.name == "QgisSdkPlugin"
        }
        self.applications: set[str] = set()
        for statement in tree.body:
            if not isinstance(statement, ast.Assign | ast.AnnAssign) or not isinstance(
                statement.value, ast.Call
            ):
                continue
            target = statement.value.func
            is_constructor = isinstance(target, ast.Name) and target.id in constructors
            is_constructor |= (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in self.modules
                and target.attr == "QgisSdkPlugin"
            )
            if is_constructor:
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                self.applications.update(
                    name.id for name in targets if isinstance(name, ast.Name)
                )

    def is_surface(self, node: ast.ClassDef) -> bool:
        """Whether the class subclasses ``Dialog``/``Dock`` as this module spells them."""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in self.surfaces:
                return True
            if (
                isinstance(base, ast.Attribute)
                and base.attr in _SURFACES
                and isinstance(base.value, ast.Attribute | ast.Name)
                and ast.unparse(base.value) in _UI_MODULES
            ):
                return True
        return False

    def on_target(self, decorator: ast.expr) -> ast.expr | None:
        """The first argument of ``@on(...)`` however the decorator is spelled.

        ``@on("x").changed``, ``@on("x", "sig")``, ``@ui.on("x")`` and an
        alias ``from qgis_sdk.ui import on as wired`` all count.
        """
        call = decorator.value if isinstance(decorator, ast.Attribute) else decorator
        if not isinstance(call, ast.Call) or not call.args:
            return None
        func = call.func
        if isinstance(func, ast.Name):
            return call.args[0] if func.id in self.on else None
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "on"
            and ast.unparse(func.value) in _UI_MODULES
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
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in self.modules
            and target.attr in _BINDINGS
        ):
            return target.attr
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in self.applications
            and target.attr == "action"
        ):
            return "action"
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


def _check_surface_widgets(node: ast.ClassDef, path: Path) -> Iterator[Diagnostic]:
    """UI001: an interactive widget built in a surface method without an objectName."""
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        named: set[str] = set()
        holders: dict[int, str | None] = {}
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
        for call in ast.walk(method):
            if not isinstance(call, ast.Call):
                continue
            widget = _callee_name(call)
            if widget not in INTERACTIVE_WIDGETS:
                continue
            target = holders.get(id(call))
            if target is not None and target in named:
                continue
            where = f"{node.name}.{method.name}()"
            subject = f"{target} ({widget})" if target else f"an unassigned {widget}"
            yield Diagnostic(
                rule="UI001",
                path=path,
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


def _check_ui_names(
    node: ast.ClassDef, names: _Names, path: Path, directory: Path
) -> Iterator[Diagnostic]:
    """UI002: ``@on`` over a Designer file that declares no such widget."""
    ui = _class_constant(node, "ui")
    if not isinstance(ui, str) or not ui:
        return
    file = directory / ui
    try:
        declared = ui_names(file)
    except QgisSdkUiError as error:
        shown = file if Path(ui).is_absolute() else path.parent / ui
        reason = "does not exist" if not file.is_file() else str(error)
        yield Diagnostic(
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
        return
    known = ", ".join(declared) or "none"
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in method.decorator_list:
            target = names.on_target(decorator)
            name = _literal_name(target, names)
            if name is None or name in declared:
                continue
            yield Diagnostic(
                rule="UI002",
                path=path,
                line=decorator.lineno,
                column=decorator.col_offset + 1,
                message=(
                    f"@on({name!r}) in {node.name}: {ui} declares no "
                    f"widget named {name!r}"
                ),
                remediation=(
                    f"Use one of the objectNames the file declares ({known}) or "
                    "name the widget in Qt Designer; wiring fails when the "
                    "surface opens otherwise."
                ),
            )


def _check_declared(
    node: ast.ClassDef, names: _Names, path: Path
) -> Iterator[Diagnostic]:
    """UI005: the declarative form, as far as the source shows it."""
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
            for name in _bound_names(statement):
                bound.setdefault(name, None)
    for attribute, value in bound.items():
        if isinstance(value, ast.Call) and _callee_name(value) == "Custom":
            widget = _custom_widget(value)
            if isinstance(widget, ast.Call):
                yield Diagnostic(
                    rule="UI005",
                    path=path,
                    line=value.lineno,
                    column=value.col_offset + 1,
                    message=(
                        f"{node.name}.{attribute} = Custom({_callee_name(widget)}"
                        "(...)): a widget built when the class is defined cannot "
                        "be copied for each window"
                    ),
                    remediation=(
                        "Pass Custom the widget class or a factory "
                        "(Custom(widget=QLabel), Custom(lambda parent: ...)); it "
                        "runs once per opening, when the tree is mounted."
                    ),
                )
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in method.decorator_list:
            target = names.on_target(decorator)
            if not isinstance(target, ast.Name) or target.id in names.constants:
                continue
            name = target.id
            if name in bound:
                value = bound[name]
                kind = _literal_kind(value)
                if kind is None:
                    continue  # a call, a name, an attribute: the host resolves it
                message = (
                    f"@on({name}) in {node.name}: {name!r} is {kind}, not a component"
                )
                remediation = (
                    f"Assign a catalogue component to the class attribute "
                    f"({name} = Button(text=...)) and wire @on({name}), or pass "
                    f"the widget's objectName as a string: @on({name!r})."
                )
            elif name in names.module_names:
                continue  # a module-level component or import: the host decides
            else:
                message = (
                    f"@on({name}) in {node.name}: the class declares no component "
                    f"named {name!r}"
                )
                remediation = (
                    f"Declare the component as a class attribute ({name} = "
                    f"Button(text=...)) above the method, or pass the widget's "
                    f"objectName as a string: @on({name!r})."
                )
            yield Diagnostic(
                rule="UI005",
                path=path,
                line=decorator.lineno,
                column=decorator.col_offset + 1,
                message=message,
                remediation=remediation,
            )


def _custom_widget(call: ast.Call) -> ast.expr | None:
    """The ``widget`` argument of a ``Custom(...)`` call, however it is passed."""
    for keyword in call.keywords:
        if keyword.arg == "widget":
            return keyword.value
    positional = list(call.args)
    if positional and isinstance(positional[0], ast.Constant):
        positional = positional[1:]  # Custom("name", widget)
    return positional[0] if positional else None


def _literal_kind(value: ast.expr | None) -> str | None:
    """``"a str"``/``"an int"``/``"a list"`` for a literal, ``None`` for the rest."""
    if isinstance(value, ast.Constant):
        name = type(value.value).__name__
    elif isinstance(value, ast.List | ast.Tuple | ast.Dict | ast.Set):
        name = type(value).__name__.lower()
    else:
        return None
    article = "an" if name[0] in "aeiou" else "a"
    return f"{article} {name}"


def _bound_names(statement: ast.stmt) -> Iterator[str]:
    """The names a statement binds in its scope, as far as a checker needs."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        yield statement.name
    elif isinstance(statement, ast.Import | ast.ImportFrom):
        for alias in statement.names:
            yield alias.asname or alias.name.split(".")[0]
    elif isinstance(statement, ast.Assign):
        for target in statement.targets:
            yield from _names_in(target)
    elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
        yield from _names_in(statement.target)
    elif isinstance(statement, ast.For | ast.With | ast.If | ast.Try):
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.stmt):
                yield from _bound_names(child)
        if isinstance(statement, ast.For):
            yield from _names_in(statement.target)


def _names_in(target: ast.expr) -> Iterator[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _names_in(element)


def _literal_name(target: ast.expr | None, names: _Names) -> str | None:
    """The node name an ``@on`` target spells, when the checker can read it.

    A string literal, or a module-level ``NAME = "literal"``; a component
    declared on the class (``@on(clear)``) or anything else is left to the
    host, which resolves it when the surface opens.
    """
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        return target.value
    if isinstance(target, ast.Name):
        return names.constants.get(target.id)
    return None


def _class_constant(node: ast.ClassDef, name: str) -> object:
    for statement in node.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets = [statement.target]
            value = statement.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return value.value if isinstance(value, ast.Constant) else None
    return None


def _callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""
