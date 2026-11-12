"""The probes: classify one node of a job body, first claim wins."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from ..diagnostics import Diagnostic
from ._constants import _DYNAMIC_IMPORTS, WORKER_SAFE_ATTRIBUTES, is_gui_path
from ._diagnostics import context_diagnostic, dynamic_diagnostic, gui_diagnostic
from ._module import Module

__all__ = ["JobCheck", "diagnose_node"]


def _is_context_attribute(node: ast.AST, context: str | None) -> bool:
    """Whether ``node`` reads an attribute of the worker's context argument."""
    if context is None or not isinstance(node, ast.Attribute):
        return False
    return isinstance(node.value, ast.Name) and node.value.id == context


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


def local_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
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


def imports_in_body(
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


def context_parameter(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The name of the injected context: the job's first positional parameter."""
    positional = (*function.args.posonlyargs, *function.args.args)
    return positional[0].arg if positional else None


@dataclass(frozen=True, slots=True)
class JobCheck:
    """Everything the probes need to classify one node of a job body."""

    name: str
    module: Module
    path: Path
    context: str | None
    local: set[str]
    imports: dict[str, str]
    gui_bindings: dict[str, str]


#: A probe returns ``None`` when the node is not its shape, ``_HANDLED`` when it
#: classified the node with no finding, or one Diagnostic to report.
_HANDLED = object()
_Probe = Callable[[ast.AST, JobCheck], object]


def _dynamic_probe(node: ast.AST, check: JobCheck) -> object:
    if (
        isinstance(node, ast.Call)
        and check.module.dotted(node.func) in _DYNAMIC_IMPORTS
    ):
        return dynamic_diagnostic(check.name, node, check.path)
    return None


def _context_probe(node: ast.AST, check: JobCheck) -> object:
    if not _is_context_attribute(node, check.context):
        return None
    if node.attr in WORKER_SAFE_ATTRIBUTES:
        return _HANDLED
    return context_diagnostic(check.name, check.context, node, check.path)


def _import_probe(node: ast.AST, check: JobCheck) -> object:
    if not (isinstance(node, ast.Name) and node.id in check.imports):
        return None
    dotted = check.imports[node.id]
    if is_gui_path(dotted):
        return gui_diagnostic(check.name, dotted, node, check.path, attribute=node.id)
    return _HANDLED


def _local_probe(node: ast.AST, check: JobCheck) -> object:
    if isinstance(node, ast.Name) and node.id in check.local:
        return _HANDLED
    return None


def _binding_probe(node: ast.AST, check: JobCheck) -> object:
    if not isinstance(node, ast.Name):
        return None
    bound = check.gui_bindings.get(node.id)
    if bound is not None:
        return gui_diagnostic(check.name, bound, node, check.path, attribute=node.id)
    return None


def _expression_probe(node: ast.AST, check: JobCheck) -> object:
    expression = node.func if isinstance(node, ast.Call) else node
    if not isinstance(expression, (ast.Name, ast.Attribute)):
        return _HANDLED
    if isinstance(expression, ast.Name) and (
        expression.id in check.local or not isinstance(expression.ctx, ast.Load)
    ):
        return _HANDLED
    dotted = check.module.dotted(expression)
    if dotted is not None and is_gui_path(dotted):
        return gui_diagnostic(check.name, dotted, node, check.path)
    return _HANDLED


_PROBES: tuple[_Probe, ...] = (
    _dynamic_probe,
    _context_probe,
    _import_probe,
    _local_probe,
    _binding_probe,
    _expression_probe,
)


def diagnose_node(node: ast.AST, check: JobCheck) -> Diagnostic | None:
    """The first probe that claims the node decides its one finding, if any."""
    for probe in _PROBES:
        result = probe(node, check)
        if result is not None:
            return result if isinstance(result, Diagnostic) else None
    return None
