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

import ast as _ast
from collections.abc import Iterator as _Iterator
from pathlib import Path as _Path

from ..diagnostics import Diagnostic as _Diagnostic
from ._constants import GUI_CLASSES, GUI_ONLY_PATHS, WORKER_SAFE_ATTRIBUTES
from ._module import Module as _Module
from ._probes import JobCheck as _JobCheck
from ._probes import context_parameter as _context_parameter
from ._probes import diagnose_node as _diagnose_node
from ._probes import imports_in_body as _imports_in_body
from ._probes import local_names as _local_names

__all__ = [
    "GUI_CLASSES",
    "GUI_ONLY_PATHS",
    "WORKER_SAFE_ATTRIBUTES",
    "check_jobs",
]


def check_jobs(source: str, *, path: _Path) -> _Iterator[_Diagnostic]:
    """Yield the worker-safety findings of every job in ``source``, in order.

    ``path`` is the root-relative path the diagnostics report. A file that does
    not parse is left to ``SYNTAX001`` from :func:`~.imports.check_source`, and
    a file with no job in it produces nothing.
    """
    try:
        tree = _ast.parse(source, filename=str(path))
    except SyntaxError:
        return
    module = _Module(tree)
    findings: dict[tuple[str, int, int], _Diagnostic] = {}
    for function in module.jobs():
        for diagnostic in _diagnose(function, module, path):
            findings.setdefault(
                (diagnostic.rule, diagnostic.line, diagnostic.column), diagnostic
            )
    yield from (findings[key] for key in sorted(findings))


def _body_nodes(function: _ast.FunctionDef | _ast.AsyncFunctionDef) -> list[_ast.AST]:
    """Only the body: annotations and defaults run on the driving thread."""
    nodes: list[_ast.AST] = []
    for statement in function.body:
        nodes.extend(_ast.walk(statement))
    return nodes


def _diagnose(
    function: _ast.FunctionDef | _ast.AsyncFunctionDef,
    module: _Module,
    path: _Path,
) -> _Iterator[_Diagnostic]:
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
