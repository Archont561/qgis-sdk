"""What a module's names mean, resolved without importing anything.

Two rules read declarations by their dotted path - the job rules in :mod:`.jobs`
and the host rules in :mod:`.hosts` - and both have to survive
``import qgis_sdk as sdk`` and ``from qgis_sdk import toolbar as bar``. One
resolver does that work for both (decision-8: the source is read, nothing is
imported).
"""

from __future__ import annotations

import ast


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_bind_p1(_s):
    for alias in _s.node.names:
        _s.alias = alias
        _s.local = _s.alias.asname or _s.alias.name.split(".")[0]
        _s.self.imports[_s.local] = _s.alias.name if _s.alias.asname else _s.local


def _cc_bind_p2(_s):
    for alias in _s.node.names:
        _s.alias = alias
        if _s.alias.name == "*":
            continue
        _s.self.imports[_s.alias.asname or _s.alias.name] = (
            f"{_s.node.module}.{_s.alias.name}"
        )


def _cc_bind_p3(_s):
    for target in _s.node.targets:
        _s.target = target
        if isinstance(_s.target, ast.Name):
            _s.self.assignments[_s.target.id] = _s.node.value


def _cc_bind_p4(_s):
    _s.self.assignments[_s.node.target.id] = _s.node.value


def _cc_bind_dispatch(node):
    """Choose the binding phase by the node's own type, not a branch chain."""
    if isinstance(node, ast.Import):
        return _cc_bind_p1
    if isinstance(node, ast.ImportFrom) and node.module and not node.level:
        return _cc_bind_p2
    if isinstance(node, ast.Assign):
        return _cc_bind_p3
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
    ):
        return _cc_bind_p4
    return None


def _cc_bind_p5(_s):
    phase = _cc_bind_dispatch(_s.node)
    return None if phase is None else phase(_s)


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
        _s = _CcState(**locals())
        for _p in (_cc_bind_p5,):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r.value
        return None

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
