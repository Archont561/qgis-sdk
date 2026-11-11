"""JOB001 / JOB002 / JOB003: a job body that cannot safely run on a worker.

Since 0.9.0 a ``@job`` body runs in its entirety on a worker thread
(decision-65), so everything the body does happens there. ``check`` reads the
source and reports what that means (TASK-117) - early feedback, never proof of
thread safety:

``JOB001`` - the body reads GUI state: the QGIS interface (``iface``,
``qgis.utils.iface``), a Qt or QGIS GUI class, the live project
(``QgsProject.instance()``), or a module-level name that holds one of those.
``JOB002`` - the body reads a context attribute other than ``progress`` and
``cancellation``. A job body is handed a ``WorkerContext``, which refuses every
driving-thread capability by name, so the job fails on its first step instead
of at the end.
``JOB003`` (warning) - the body imports a module by name
(``importlib.import_module``, ``__import__``), which this check cannot follow.

The decorators are recognised through the names the module imports from
``qgis_sdk``, aliases included, in both spellings: ``@job(...)`` and the
``@app.job(...)`` form A plugin uses next to its class. A name the job rebinds
locally - a parameter called ``iface``, an assignment in the body - is not
reported, because that is not the module-level binding.

What this cannot do is as important as what it can. A helper the body calls, a
live object passed in as an argument, and anything a by-name import reaches are
outside source reading; ``qgis_sdk`` therefore also refuses a GUI-bound
capability read off the thread that assembled the context, once per capability
and thread (decision-69), which catches exactly the captured-reference case.
Neither half proves thread safety. Prepare GUI state before submitting and
apply GUI changes in a callback, which is delivered on the driving thread.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .diagnostics import Diagnostic
from .names import ModuleNames

__all__ = [
    "GUI_CLASSES",
    "GUI_ONLY_PATHS",
    "WORKER_SAFE_ATTRIBUTES",
    "check_jobs",
]

#: What a ``WorkerContext`` carries; every other attribute is refused by name.
WORKER_SAFE_ATTRIBUTES = frozenset({"cancellation", "progress"})

#: Dotted paths that only mean something on the thread that owns the GUI.
GUI_ONLY_PATHS = frozenset(
    {
        "qgis.utils.iface",
        "qgis.gui.QgsInterface",
        "QgsProject.instance",
        "QgsApplication.activeWindow",
    }
)

#: Widget, canvas and interface classes: constructing or touching one from a
#: worker thread is a crash rather than a slow call. Matched on the last
#: segment of the resolved name, so an import alias is caught too. Deliberately
#: not every ``qgis.core`` class: reading a layer's data on a worker is a
#: documented hazard, not something a source check can call wrong.
GUI_CLASSES = frozenset(
    {
        # Qt
        "QApplication",
        "QDialog",
        "QDialogButtonBox",
        "QFileDialog",
        "QInputDialog",
        "QMainWindow",
        "QMessageBox",
        "QProgressDialog",
        "QWidget",
        # QGIS GUI
        "QgsDockWidget",
        "QgsFileWidget",
        "QgsGui",
        "QgsMapCanvas",
        "QgsMapCanvasItem",
        "QgsMapLayerComboBox",
        "QgsMapTool",
        "QgsMessageBar",
        "QgsOptionsDialogBase",
        "QgsProjectionSelectionWidget",
    }
)

_SDK_MODULES = frozenset({"qgis_sdk", "qgis_sdk.jobs", "qgis_sdk.declarations"})
_JOB_DECORATORS = frozenset(
    {"job", "qgis_sdk.job", "qgis_sdk.jobs.job", "qgis_sdk.declarations.job"}
)
_DYNAMIC_IMPORTS = frozenset({"importlib.import_module", "__import__"})


def _is_context_attribute(node: ast.AST, context: str | None) -> bool:
    """Whether ``node`` reads an attribute of the worker's context argument."""
    if context is None or not isinstance(node, ast.Attribute):
        return False
    return isinstance(node.value, ast.Name) and node.value.id == context


def check_jobs(source: str, *, path: Path) -> Iterator[Diagnostic]:
    """Yield the worker-safety findings of every job in ``source``, in order.

    ``path`` is the root-relative path the diagnostics report. A file that does
    not parse is left to ``SYNTAX001`` from :func:`~.imports.check_source`, and
    a file with no job in it produces nothing.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return
    module = _Module(tree)
    findings: dict[tuple[str, int, int], Diagnostic] = {}
    for function in module.jobs():
        for diagnostic in _diagnose(function, module, path):
            findings.setdefault(
                (diagnostic.rule, diagnostic.line, diagnostic.column), diagnostic
            )
    yield from (findings[key] for key in sorted(findings))


class _Module:
    """One parsed module: what its names mean, and which functions are jobs."""

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.names = ModuleNames(tree)

    @property
    def imports(self) -> dict[str, str]:
        """The local name of every module-level import, and what it denotes."""
        return self.names.imports

    @property
    def assignments(self) -> dict[str, ast.expr]:
        """The value of every module-level assignment, by name."""
        return self.names.assignments

    def dotted(self, node: ast.expr) -> str | None:
        """The dotted path a name or attribute chain denotes, aliases resolved."""
        return self.names.dotted(node)

    def gui_bindings(self) -> dict[str, str]:
        """Module-level names that hold GUI state, and why they are named so."""
        bindings: dict[str, str] = {}
        for name, value in self.assignments.items():
            target = value.func if isinstance(value, ast.Call) else value
            dotted = self.dotted(target)
            if dotted is not None and _is_gui_path(dotted):
                bindings[name] = dotted
        return bindings

    # -- jobs --------------------------------------------------------------------

    def jobs(self) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
        """Yield the module-level functions declared as jobs, in source order."""
        for node in self.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(self._is_job_decorator(item) for item in node.decorator_list):
                yield node

    def _is_job_decorator(self, decorator: ast.expr) -> bool:
        dotted = self.names.declared_as(decorator)
        if dotted is None:
            return False
        if dotted in _JOB_DECORATORS:
            return True
        # ``@app.job(...)``: the plugin instance is a module-level name, and the
        # decorator applies ``@job`` itself (TASK-116).
        base, _, attribute = dotted.rpartition(".")
        return attribute == "job" and base not in _SDK_MODULES


def _bound_argument(node: ast.arg) -> tuple[str, ...]:
    return (node.arg,)


def _bound_definition(node: ast.AST) -> tuple[str, ...]:
    return (node.name,)


def _bound_import(node: ast.Import) -> Iterable[str]:
    return (alias.asname or alias.name.split(".")[0] for alias in node.names)


def _bound_import_from(node: ast.ImportFrom) -> Iterable[str]:
    return (alias.asname or alias.name for alias in node.names)


def _bound_except(node: ast.ExceptHandler) -> tuple[str, ...]:
    return (node.name,) if node.name else ()


#: Which names one AST node binds locally. ``Name`` with a ``Store`` context and
#: ``Global`` are handled in the loop because they depend on more than the type.
_LOCAL_BINDERS: dict[type, Callable[[ast.AST], Iterable[str]]] = {
    ast.arg: _bound_argument,
    ast.FunctionDef: _bound_definition,
    ast.AsyncFunctionDef: _bound_definition,
    ast.ClassDef: _bound_definition,
    ast.Import: _bound_import,
    ast.ImportFrom: _bound_import_from,
    ast.ExceptHandler: _bound_except,
}


def _local_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names the body binds itself, and the ones it declares ``global``.

    A locally bound name is not the module-level binding, so ``def f(ctx, iface)``
    must not be reported for using ``iface``; a ``global`` declaration brings the
    module binding back into play.
    """
    local: set[str] = set()
    globals_: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Global):
            globals_.update(node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        else:
            binder = _LOCAL_BINDERS.get(type(node))
            if binder is not None:
                local.update(binder(node))
    return local - globals_


def _imports_in_body(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, str]:
    """Names the body imports itself, and the dotted path each one denotes.

    ``from qgis.utils import iface`` inside the job is as much the interface as
    the module-level import is, so it is resolved the same way rather than
    treated as a local binding that shadows nothing.
    """
    found: dict[str, str] = {}
    for statement in function.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Import):
                found.update(_import_names(node))
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.update(_import_from_names(node))
    return found


def _import_names(node: ast.Import) -> dict[str, str]:
    """Names an ``import x.y`` binds, with the dotted path each one denotes."""
    return {
        alias.asname or alias.name.split(".")[0]: (
            alias.name if alias.asname else alias.name.split(".")[0]
        )
        for alias in node.names
    }


def _import_from_names(node: ast.ImportFrom) -> dict[str, str]:
    """Names a ``from x import y`` binds, each with its fully qualified path."""
    return {
        alias.asname or alias.name: f"{node.module}.{alias.name}"
        for alias in node.names
        if alias.name != "*"
    }


def _context_parameter(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The name of the injected context: the job's first positional parameter."""
    positional = (*function.args.posonlyargs, *function.args.args)
    return positional[0].arg if positional else None


@dataclass(frozen=True, slots=True)
class _JobCheck:
    """Everything the probes need to classify one node of a job body."""

    name: str
    module: _Module
    path: Path
    context: str | None
    local: set[str]
    imports: dict[str, str]
    gui_bindings: dict[str, str]


#: A probe returns ``None`` when the node is not its shape, ``_HANDLED`` when it
#: classified the node with no finding, or one Diagnostic to report.
_HANDLED = object()
_Probe = Callable[[ast.AST, _JobCheck], object]


def _dynamic_probe(node: ast.AST, check: _JobCheck) -> object:
    if (
        isinstance(node, ast.Call)
        and check.module.dotted(node.func) in _DYNAMIC_IMPORTS
    ):
        return _dynamic_diagnostic(check.name, node, check.path)
    return None


def _context_probe(node: ast.AST, check: _JobCheck) -> object:
    if not _is_context_attribute(node, check.context):
        return None
    if node.attr in WORKER_SAFE_ATTRIBUTES:
        return _HANDLED
    return _context_diagnostic(check.name, check.context, node, check.path)


def _import_probe(node: ast.AST, check: _JobCheck) -> object:
    if not (isinstance(node, ast.Name) and node.id in check.imports):
        return None
    dotted = check.imports[node.id]
    if _is_gui_path(dotted):
        return _gui_diagnostic(check.name, dotted, node, check.path, attribute=node.id)
    return _HANDLED


def _local_probe(node: ast.AST, check: _JobCheck) -> object:
    if isinstance(node, ast.Name) and node.id in check.local:
        return _HANDLED
    return None


def _binding_probe(node: ast.AST, check: _JobCheck) -> object:
    if not isinstance(node, ast.Name):
        return None
    bound = check.gui_bindings.get(node.id)
    if bound is not None:
        return _gui_diagnostic(check.name, bound, node, check.path, attribute=node.id)
    return None


def _expression_probe(node: ast.AST, check: _JobCheck) -> object:
    expression = node.func if isinstance(node, ast.Call) else node
    if not isinstance(expression, (ast.Name, ast.Attribute)):
        return _HANDLED
    if isinstance(expression, ast.Name) and (
        expression.id in check.local or not isinstance(expression.ctx, ast.Load)
    ):
        return _HANDLED
    dotted = check.module.dotted(expression)
    if dotted is not None and _is_gui_path(dotted):
        return _gui_diagnostic(check.name, dotted, node, check.path)
    return _HANDLED


_PROBES: tuple[_Probe, ...] = (
    _dynamic_probe,
    _context_probe,
    _import_probe,
    _local_probe,
    _binding_probe,
    _expression_probe,
)


def _diagnose_node(node: ast.AST, check: _JobCheck) -> Diagnostic | None:
    """The first probe that claims the node decides its one finding, if any."""
    for probe in _PROBES:
        result = probe(node, check)
        if result is not None:
            return result if isinstance(result, Diagnostic) else None
    return None


def _body_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Only the body: annotations and defaults run on the driving thread."""
    nodes: list[ast.AST] = []
    for statement in function.body:
        nodes.extend(ast.walk(statement))
    return nodes


def _diagnose(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    module: _Module,
    path: Path,
) -> Iterator[Diagnostic]:
    """Every worker-safety finding inside one job body."""
    check = _JobCheck(
        name=function.name,
        module=module,
        path=path,
        context=_context_parameter(function),
        local=_local_names(function),
        imports=_imports_in_body(function),
        gui_bindings=module.gui_bindings(),
    )
    for node in _body_nodes(function):
        finding = _diagnose_node(node, check)
        if finding is not None:
            yield finding


def _is_gui_path(dotted: str) -> bool:
    """Whether a resolved dotted path is GUI state or a GUI class."""
    if any(dotted == item or dotted.endswith(f".{item}") for item in GUI_ONLY_PATHS):
        return True
    return dotted.rpartition(".")[2] in GUI_CLASSES


def _gui_diagnostic(
    job: str,
    dotted: str,
    node: ast.expr,
    path: Path,
    *,
    attribute: str | None = None,
) -> Diagnostic:
    """``JOB001`` for one piece of GUI state a job body reaches."""
    shown = f"`{attribute}` (bound to `{dotted}`)" if attribute else f"`{dotted}`"
    return Diagnostic(
        rule="JOB001",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"job `{job}` reaches {shown} in its body, which belongs to the GUI thread"
        ),
        remediation=(
            "Do the GUI work on the driving thread: open the surface or read the "
            "interface in an action, pass plain values (paths, ids, numbers) into the "
            "job, and update the UI in the success callback (decision-65)."
        ),
    )


def _context_diagnostic(
    job: str, context: str, node: ast.expr, path: Path
) -> Diagnostic:
    """``JOB002`` for one driving-thread capability read from a job body."""
    attribute = getattr(node, "attr", "")
    return Diagnostic(
        rule="JOB002",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"job `{job}` reads `{context}.{attribute}` in its body, which a "
            "WorkerContext refuses"
        ),
        remediation=(
            f"A job body only gets `progress` and `cancellation`. Pass plain values "
            f"in and re-read `{attribute}` from the success callback, which runs on "
            "the driving thread (decision-65)."
        ),
    )


def _dynamic_diagnostic(job: str, node: ast.expr, path: Path) -> Diagnostic:
    """``JOB003`` for a by-name import this check cannot follow."""
    return Diagnostic(
        rule="JOB003",
        path=path,
        line=node.lineno,
        column=node.col_offset + 1,
        message=(
            f"job `{job}` imports a module by name, so what the body reaches "
            "cannot be read"
        ),
        remediation=(
            "Import the module at module level or in a helper outside the job, so "
            "`qgis-sdk check` can see what the body touches; this is a warning about "
            "what the check cannot prove, not an error."
        ),
        severity="warning",
    )
