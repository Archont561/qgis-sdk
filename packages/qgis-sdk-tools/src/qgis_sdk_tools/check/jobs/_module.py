"""One parsed module: what its names mean, and which functions are jobs."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from ..names import ModuleNames
from ._constants import _JOB_DECORATORS, _SDK_MODULES, is_gui_path

__all__ = ["Module"]


class Module:
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
            if dotted is not None and is_gui_path(dotted):
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
