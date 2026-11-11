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
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _CheckContext:
    """The read-only facts one UI checker pass needs at every node."""

    names: _Names
    path: Path
    package_directory: Path | None
    directory: Path | None


@dataclass(frozen=True, slots=True)
class _ImportFacts:
    """How one module spells the imported UI and binding names."""

    bindings: dict[str, str]
    surfaces: set[str]
    on: set[str]
    modules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _WidgetSite:
    """One surface method's named widgets while UI001 walks its calls."""

    node: ast.ClassDef
    method: ast.FunctionDef | ast.AsyncFunctionDef
    path: Path
    holders: dict[int, str | None]
    named: set[str]


@dataclass(frozen=True, slots=True)
class _DeclaredSite:
    """The class attributes and module names UI005 resolves against."""

    node: ast.ClassDef
    names: _Names
    bound: dict[str, ast.expr | None]
    path: Path


@dataclass(frozen=True, slots=True)
class _UiScope:
    """The Designer-file facts one UI002 pass resolves ``@on`` against."""

    node: ast.ClassDef
    ui: str
    known: str
    declared: tuple[str, ...]
    path: Path
    error: Diagnostic | None


_MISSING = object()
_COMPOUND = (ast.For, ast.With, ast.If, ast.Try)


def _node_diagnostics(node: ast.AST, context: _CheckContext) -> Iterator[Diagnostic]:
    """Yield every finding one AST node can own."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        yield from _check_function(node, context)
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        for decorator in node.decorator_list:
            yield from _check_icon(decorator, context)
    if isinstance(node, ast.ClassDef) and context.names.is_surface(node):
        yield from _surface_diagnostics(node, context)


def _surface_diagnostics(
    node: ast.ClassDef, context: _CheckContext
) -> Iterator[Diagnostic]:
    """Yield the three checks a Dialog/Dock class owns."""
    yield from _check_surface_widgets(node, context)
    if context.directory is not None:
        yield from _check_ui_names(node, context)
    yield from _check_declared(node, context)


def check_bindings(
    source: str,
    *,
    path: Path,
    package_directory: Path | None,
    directory: Path | None = None,
) -> Iterator[Diagnostic]:
    """Yield the UI001-UI003 and ICON001 findings in ``source``, in source order.

    ``path`` is the reported path; ``package_directory`` locates ``icons/``;
    ``directory`` resolves a relative ``ui = "x.ui"``. ``None`` skips ICON001
    or UI002 respectively. Only the source is read (decision-8).
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
    context = _CheckContext(names, path, package_directory, directory)
    for node in ast.walk(tree):
        yield from _node_diagnostics(node, context)


def _import_base(
    node: ast.ImportFrom, directory: Path, package: Path, package_name: str
) -> Path | None:
    """Resolve one ImportFrom to a local module path, or refuse a foreign root."""
    parts = node.module.split(".")
    if node.level:
        base = directory
        for _ in range(node.level - 1):
            base = base.parent
    else:
        if parts[0] != package_name:
            return None
        base = package
        parts = parts[1:]
    return base.joinpath(*parts)


def _imported_names(node: ast.ImportFrom, module: Path, package: Path) -> set[str]:
    """The imported plugin names one local module actually declares."""
    for candidate in (module.with_suffix(".py"), module / "__init__.py"):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(package) or not resolved.is_file():
            continue
        try:
            imported = ast.parse(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError):
            break
        applications = _Names(imported).applications
        return {
            alias.asname or alias.name
            for alias in node.names
            if alias.name in applications
        }
    return set()


def _imported_applications(
    tree: ast.Module, directory: Path, package_directory: Path
) -> set[str]:
    """Find directly imported local plugins without importing project code."""
    found: set[str] = set()
    package = package_directory.resolve()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        module = _import_base(node, directory, package, package.name)
        if module is None:
            continue
        found.update(_imported_names(node, module, package))
    return found


def _module_names(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """Top-level bound names and the string constants ``@on(NAME)`` can read."""
    names: set[str] = set()
    constants: dict[str, str] = {}
    for statement in tree.body:
        names.update(_bound_names(statement))
        if (
            isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = statement.value.value
    return names, constants


def _constructors(tree: ast.Module) -> set[str]:
    """The local names ``QgisSdkPlugin`` was imported as."""
    return {
        alias.asname or alias.name
        for statement in tree.body
        if isinstance(statement, ast.ImportFrom) and statement.module == "qgis_sdk"
        for alias in statement.names
        if alias.name == "QgisSdkPlugin"
    }


def _is_plugin_constructor(
    node: ast.expr, constructors: set[str], modules: tuple[str, ...]
) -> bool:
    """Whether a call target constructs the plugin the way this module spells it."""
    if isinstance(node, ast.Name):
        return node.id in constructors
    if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
        return False
    return node.value.id in modules and node.attr == "QgisSdkPlugin"


def _applications(
    tree: ast.Module, constructors: set[str], modules: tuple[str, ...]
) -> set[str]:
    """The module-level names one plugin application is assigned to."""
    applications: set[str] = set()
    for statement in tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign) or not isinstance(
            statement.value, ast.Call
        ):
            continue
        if not _is_plugin_constructor(statement.value.func, constructors, modules):
            continue
        targets = (
            statement.targets
            if isinstance(statement, ast.Assign)
            else [statement.target]
        )
        applications.update(name.id for name in targets if isinstance(name, ast.Name))
    return applications


def _ui_import_aliases(node: ast.ImportFrom) -> tuple[set[str], set[str]]:
    """The surface and ``on`` aliases one UI/wiring import declares."""
    surfaces: set[str] = set()
    on: set[str] = set()
    for alias in node.names:
        if alias.name in _SURFACES and node.module in _SURFACE_SOURCES:
            surfaces.add(alias.asname or alias.name)
        elif alias.name == "on" and node.module in _WIRING_SOURCES:
            on.add(alias.asname or alias.name)
    return surfaces, on


def _binding_import_aliases(node: ast.ImportFrom, bindings: dict[str, str]) -> None:
    """Record the local spelling of toolbar/menu/shortcut imports."""
    for alias in node.names:
        local = alias.asname or alias.name
        if alias.name in _BINDINGS:
            bindings[local] = alias.name


def _module_import_aliases(node: ast.Import, modules: list[str]) -> None:
    """Record the local spelling of an imported SDK module."""
    for alias in node.names:
        if alias.name in _SOURCES:
            modules.append(alias.asname or alias.name)


def _collect_imports(tree: ast.Module) -> _ImportFacts:
    """Collect the four import vocabularies in one walk of the module."""
    bindings: dict[str, str] = {}
    surfaces: set[str] = set()
    on: set[str] = set()
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in (
            _SURFACE_SOURCES | _WIRING_SOURCES
        ):
            surfaces_part, on_part = _ui_import_aliases(node)
            surfaces.update(surfaces_part)
            on.update(on_part)
        elif isinstance(node, ast.ImportFrom) and node.module in _SOURCES:
            _binding_import_aliases(node, bindings)
        elif isinstance(node, ast.Import):
            _module_import_aliases(node, modules)
    return _ImportFacts(bindings, surfaces, on, tuple(modules))


class _Names:
    """How this module spells ``toolbar``, ``menu``, ``shortcut`` and ``action``."""

    def __init__(self, tree: ast.Module) -> None:
        facts = _collect_imports(tree)
        self.bindings = facts.bindings
        self.surfaces = facts.surfaces
        self.on = facts.on
        self.modules = facts.modules
        self.module_names, self.constants = _module_names(tree)
        self.applications = _applications(tree, _constructors(tree), self.modules)

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
            ast.unparse(node.value) in _UI_MODULES
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
            if self._is_ui_module_member(base, _SURFACES):
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
        if self._is_module_member(target, _BINDINGS):
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


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, context: _CheckContext
) -> Iterator[Diagnostic]:
    kinds = [context.names.kind(decorator) for decorator in node.decorator_list]
    bound = [kind for kind in kinds if kind in _BINDINGS]
    if not bound or "action" not in kinds:
        return
    inputs = _input_names(node)
    if not inputs:
        return
    yield _ui003(node, bound, inputs, context.path)


def _check_icon(decorator: ast.expr, context: _CheckContext) -> Iterator[Diagnostic]:
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


def _widget_diagnostic(call: ast.Call, site: _WidgetSite) -> Diagnostic | None:
    """UI001 for one interactive widget without an objectName, else ``None``."""
    widget = _callee_name(call)
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


def _check_surface_widgets(
    node: ast.ClassDef, context: _CheckContext
) -> Iterator[Diagnostic]:
    """Yield UI001 for interactive widgets built in surface methods."""
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        holders, named = _widget_holders(method)
        site = _WidgetSite(node, method, context.path, holders, named)
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


def _ui_scope(node: ast.ClassDef, context: _CheckContext) -> _UiScope | None:
    """Read the Designer file once, or record why it cannot be read."""
    ui = _class_constant(node, "ui")
    if not isinstance(ui, str) or not ui:
        return None
    file = context.directory / ui  # type: ignore[operator]
    declared, reason = _read_ui_names(file)
    if reason is not None:
        error = _ui_file_error(node, ui, file, context.path, reason)
        return _UiScope(node, ui, "", (), context.path, error)
    known = ", ".join(declared) or "none"
    return _UiScope(node, ui, known, declared, context.path, None)


def _ui_name_diagnostic(decorator: ast.expr, name: str, scope: _UiScope) -> Diagnostic:
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


def _check_ui_names(node: ast.ClassDef, context: _CheckContext) -> Iterator[Diagnostic]:
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
            name = _literal_name(context.names.on_target(decorator), context.names)
            if name is None or name in scope.declared:
                continue
            yield _ui_name_diagnostic(decorator, name, scope)


def _bound_attributes(node: ast.ClassDef) -> dict[str, ast.expr | None]:
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
            for name in _bound_names(statement):
                bound.setdefault(name, None)
    return bound


def _custom_diagnostic(
    attribute: str, value: ast.expr | None, site: _DeclaredSite
) -> Diagnostic | None:
    """UI005 for a ``Custom`` holding a widget built at class definition time."""
    if not isinstance(value, ast.Call) or _callee_name(value) != "Custom":
        return None
    widget = _custom_widget(value)
    if not isinstance(widget, ast.Call):
        return None
    return Diagnostic(
        rule="UI005",
        path=site.path,
        line=value.lineno,
        column=value.col_offset + 1,
        message=(
            f"{site.node.name}.{attribute} = Custom({_callee_name(widget)}"
            "(...)): a widget built when the class is defined cannot "
            "be copied for each window"
        ),
        remediation=(
            "Pass Custom the widget class or a factory "
            "(Custom(widget=QLabel), Custom(lambda parent: ...)); it "
            "runs once per opening, when the tree is mounted."
        ),
    )


def _literal_on_diagnostic(
    name: str, kind: str, site: _DeclaredSite
) -> tuple[str, str]:
    """The UI005 wording for a class attribute that is a literal, not a component."""
    return (
        f"@on({name}) in {site.node.name}: {name!r} is {kind}, not a component",
        (
            f"Assign a catalogue component to the class attribute "
            f"({name} = Button(text=...)) and wire @on({name}), or pass "
            f"the widget's objectName as a string: @on({name!r})."
        ),
    )


def _missing_on_diagnostic(name: str, site: _DeclaredSite) -> tuple[str, str]:
    """The UI005 wording for an ``@on`` name the class never declares."""
    return (
        (
            f"@on({name}) in {site.node.name}: the class declares no component "
            f"named {name!r}"
        ),
        (
            f"Declare the component as a class attribute ({name} = "
            f"Button(text=...)) above the method, or pass the widget's "
            f"objectName as a string: @on({name!r})."
        ),
    )


def _on_diagnostic(
    decorator: ast.expr, name: str, site: _DeclaredSite
) -> Diagnostic | None:
    """UI005 for an ``@on(NAME)`` that resolves to no component."""
    value = site.bound.get(name, _MISSING)
    if value is not _MISSING:
        kind = _literal_kind(value)  # type: ignore[arg-type]
        if kind is None:
            return None  # a call, a name, an attribute: the host resolves it
        message, remediation = _literal_on_diagnostic(name, kind, site)
    elif name in site.names.module_names:
        return None  # a module-level component or import: the host decides
    else:
        message, remediation = _missing_on_diagnostic(name, site)
    return Diagnostic(
        rule="UI005",
        path=site.path,
        line=decorator.lineno,
        column=decorator.col_offset + 1,
        message=message,
        remediation=remediation,
    )


def _check_declared(node: ast.ClassDef, context: _CheckContext) -> Iterator[Diagnostic]:
    """Yield UI005 for the declarative form, as far as the source shows it."""
    bound = _bound_attributes(node)
    site = _DeclaredSite(node, context.names, bound, context.path)
    for attribute, value in bound.items():
        diagnostic = _custom_diagnostic(attribute, value, site)
        if diagnostic is not None:
            yield diagnostic
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in method.decorator_list:
            target = site.names.on_target(decorator)
            if not isinstance(target, ast.Name) or target.id in site.names.constants:
                continue
            diagnostic = _on_diagnostic(decorator, target.id, site)
            if diagnostic is not None:
                yield diagnostic


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


def _child_statements(statement: ast.stmt) -> Iterator[ast.stmt]:
    """The nested statements a compound statement may bind names in."""
    for child in ast.iter_child_nodes(statement):
        if isinstance(child, ast.stmt):
            yield child


def _bound_names(statement: ast.stmt) -> Iterator[str]:
    """The names a statement binds in its scope, as far as a checker needs."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        yield statement.name
        return
    if isinstance(statement, ast.Import | ast.ImportFrom):
        for alias in statement.names:
            yield alias.asname or alias.name.split(".")[0]
        return
    if isinstance(statement, ast.Assign):
        for target in statement.targets:
            yield from _names_in(target)
        return
    if isinstance(statement, ast.AnnAssign | ast.AugAssign):
        yield from _names_in(statement.target)
        return
    if isinstance(statement, _COMPOUND):
        for child in _child_statements(statement):
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
