"""What a module's names mean, resolved without importing anything.

Two rules read declarations by their dotted path - the job rules in :mod:`.jobs`
and the host rules in :mod:`.hosts` - and both have to survive
``import qgis_sdk as sdk`` and ``from qgis_sdk import toolbar as bar``. One
resolver does that work for both (decision-8: the source is read, nothing is
imported).
"""

from __future__ import annotations

import ast

__all__ = ["ModuleNames"]


class ModuleNames:
    """The import and assignment bindings of one parsed module.

    ``imports`` maps a local name to the dotted path it denotes; ``assignments``
    keeps module-level values so a caller can tell whether a name holds
    something interesting. Both are built from the module body only, so a name
    bound inside a function is not mistaken for the module-level binding.
    """

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.imports: dict[str, str] = {}
        self.assignments: dict[str, ast.expr] = {}
        for node in tree.body:
            self._bind(node)

    def _bind(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                self.imports[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name == "*":
                    continue
                self.imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.assignments[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            self.assignments[node.target.id] = node.value

    def dotted(self, node: ast.expr) -> str | None:
        """The dotted path a name or attribute chain denotes, aliases resolved."""
        if isinstance(node, ast.Name):
            return self.imports.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self.dotted(node.value)
            return f"{base}.{node.attr}" if base is not None else None
        return None

    def declared_as(self, decorator: ast.expr) -> str | None:
        """The dotted path of a decorator, called or bare."""
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        return self.dotted(target)
