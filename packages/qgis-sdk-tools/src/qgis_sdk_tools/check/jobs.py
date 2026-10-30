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
from collections.abc import Iterator
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


def _is_gui_path(dotted: str) -> bool:
    """Whether a resolved dotted path is GUI state or a GUI class."""
    if dotted in GUI_ONLY_PATHS:
        return True
    return dotted.rpartition(".")[2] in GUI_CLASSES


def _local_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names the body binds itself, and the ones it declares ``global``.

    A locally bound name is not the module-level binding, so ``def f(ctx, iface)``
    must not be reported for using ``iface``; a ``global`` declaration brings the
    module binding back into play.
    """
    local: set[str] = set()
    globals_: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.arg):
            local.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(node.name)
        elif isinstance(node, ast.Import):
            local.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            local.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            local.add(node.name)
        elif isinstance(node, ast.Global):
            globals_.update(node.names)
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
                for alias in node.names:
                    found[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    if alias.name != "*":
                        found[alias.asname or alias.name] = (
                            f"{node.module}.{alias.name}"
                        )
    return found


def _context_parameter(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The name of the injected context: the job's first positional parameter."""
    positional = (*function.args.posonlyargs, *function.args.args)
    return positional[0].arg if positional else None


def _diagnose(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    module: _Module,
    path: Path,
) -> Iterator[Diagnostic]:
    """Every worker-safety finding inside one job body."""
    name = function.name
    local = _local_names(function)
    imports = _imports_in_body(function)
    gui_bindings = module.gui_bindings()
    context = _context_parameter(function)
    # Only the body: an annotation or a default value is evaluated when the
    # module is defined, on the driving thread, not on the worker.
    nodes: list[ast.AST] = []
    for statement in function.body:
        nodes.extend(ast.walk(statement))
    for node in nodes:
        if isinstance(node, ast.Call) and module.dotted(node.func) in _DYNAMIC_IMPORTS:
            yield _dynamic_diagnostic(name, node, path)
            continue
        if (
            isinstance(node, ast.Attribute)
            and context is not None
            and isinstance(node.value, ast.Name)
            and node.value.id == context
        ):
            if node.attr not in WORKER_SAFE_ATTRIBUTES:
                yield _context_diagnostic(name, context, node, path)
            continue
        if isinstance(node, ast.Name) and node.id in imports:
            dotted = imports[node.id]
            if _is_gui_path(dotted):
                yield _gui_diagnostic(name, dotted, node, path, attribute=node.id)
            continue
        if isinstance(node, ast.Name) and node.id in local:
            continue
        if isinstance(node, ast.Name):
            bound = gui_bindings.get(node.id)
            if bound is not None:
                yield _gui_diagnostic(name, bound, node, path, attribute=node.id)
                continue
        expression = node.func if isinstance(node, ast.Call) else node
        if not isinstance(expression, (ast.Name, ast.Attribute)):
            continue
        if isinstance(expression, ast.Name) and (
            expression.id in local or not isinstance(expression.ctx, ast.Load)
        ):
            continue
        dotted = module.dotted(expression)
        if dotted is not None and _is_gui_path(dotted):
            yield _gui_diagnostic(name, dotted, node, path)


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
