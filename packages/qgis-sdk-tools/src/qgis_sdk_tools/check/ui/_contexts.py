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
from typing import TYPE_CHECKING

from qgis_sdk_tools.check.diagnostics import Diagnostic

if TYPE_CHECKING:
    from qgis_sdk_tools.check.ui._functions import Names

ICON_DIRECTORY = "icons"
BINDINGS = frozenset({"toolbar", "menu", "shortcut"})
_SOURCES = frozenset({"qgis_sdk", "qgis_sdk.bindings", "qgis_sdk.declarations"})
_SURFACE_SOURCES = frozenset({"qgis_sdk.ui", "qgis_sdk.ui.surfaces"})
_WIRING_SOURCES = frozenset({"qgis_sdk.ui", "qgis_sdk.ui.wiring"})
UI_MODULES = frozenset({"qgis_sdk.ui", "ui"})
SURFACES = frozenset({"Dialog", "Dock"})
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
class CheckContext:
    """The read-only facts one UI checker pass needs at every node."""

    names: Names
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
class WidgetSite:
    """One surface method's named widgets while UI001 walks its calls."""

    node: ast.ClassDef
    method: ast.FunctionDef | ast.AsyncFunctionDef
    path: Path
    holders: dict[int, str | None]
    named: set[str]


@dataclass(frozen=True, slots=True)
class DeclaredSite:
    """The class attributes and module names UI005 resolves against."""

    node: ast.ClassDef
    names: Names
    bound: dict[str, ast.expr | None]
    path: Path


@dataclass(frozen=True, slots=True)
class UiScope:
    """The Designer-file facts one UI002 pass resolves ``@on`` against."""

    node: ast.ClassDef
    ui: str
    known: str
    declared: tuple[str, ...]
    path: Path
    error: Diagnostic | None


MISSING = object()
COMPOUND = (ast.For, ast.With, ast.If, ast.Try)


def _node_diagnostics(node: ast.AST, context: CheckContext) -> Iterator[Diagnostic]:
    """Yield every finding one AST node can own."""
    from ._functions import check_function, check_icon

    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        yield from check_function(node, context)
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        for decorator in node.decorator_list:
            yield from check_icon(decorator, context)
    if isinstance(node, ast.ClassDef) and context.names.is_surface(node):
        yield from _surface_diagnostics(node, context)


def _surface_diagnostics(
    node: ast.ClassDef, context: CheckContext
) -> Iterator[Diagnostic]:
    """Yield the three checks a Dialog/Dock class owns."""
    from ._functions import check_surface_widgets, check_ui_names

    yield from check_surface_widgets(node, context)
    if context.directory is not None:
        yield from check_ui_names(node, context)
    from ._declared import check_declared

    yield from check_declared(node, context)


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
    from ._functions import Names

    names = Names(tree)
    if directory is not None and package_directory is not None:
        names.applications.update(
            _imported_applications(tree, directory, package_directory)
        )
    if not names.bindings and names.modules == () and not names.surfaces:
        return
    context = CheckContext(names, path, package_directory, directory)
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
        from ._functions import Names

        applications = Names(imported).applications
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


def module_names(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """Top-level bound names and the string constants ``@on(NAME)`` can read."""
    names: set[str] = set()
    constants: dict[str, str] = {}
    for statement in tree.body:
        from ._declared import bound_names

        names.update(bound_names(statement))
        if (
            isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = statement.value.value
    return names, constants


def constructors(tree: ast.Module) -> set[str]:
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


def applications(
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
        if alias.name in SURFACES and node.module in _SURFACE_SOURCES:
            surfaces.add(alias.asname or alias.name)
        elif alias.name == "on" and node.module in _WIRING_SOURCES:
            on.add(alias.asname or alias.name)
    return surfaces, on


def _binding_import_aliases(node: ast.ImportFrom, bindings: dict[str, str]) -> None:
    """Record the local spelling of toolbar/menu/shortcut imports."""
    for alias in node.names:
        local = alias.asname or alias.name
        if alias.name in BINDINGS:
            bindings[local] = alias.name


def _module_import_aliases(node: ast.Import, modules: list[str]) -> None:
    """Record the local spelling of an imported SDK module."""
    for alias in node.names:
        if alias.name in _SOURCES:
            modules.append(alias.asname or alias.name)


def collect_imports(tree: ast.Module) -> _ImportFacts:
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
