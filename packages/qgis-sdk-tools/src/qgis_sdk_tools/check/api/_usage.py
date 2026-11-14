"""Find the imports in one file that name a deprecated symbol.

Two spellings reach a name: ``from qgis_sdk.ui import OldPanel`` binds it
directly, and ``import qgis_sdk.models as models`` reaches it through a dotted
attribute. Both are read here; the module aliases are resolved first so an alias
is not a blind spot.

Only the imports are reported. A name the file imported and then used is the
same finding, and the line that names it is the one a reader can act on.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from qgis_sdk.deprecation import Deprecation

from ._table import Marks

__all__ = ["deprecated_uses"]


def _aliases(tree: ast.AST) -> dict[str, str]:
    """``import qgis_sdk.models as models`` -> ``{"models": "qgis_sdk.models"}``."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = alias.name
    return found


def _dotted(node: ast.AST) -> str:
    """``a.b.c`` for a chain of attributes, or ``""`` when it is not one."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    return ".".join([node.id, *reversed(parts)])


def _resolved(dotted: str, aliases: dict[str, str]) -> str:
    """Rewrite a chain that starts at a module alias into its real module."""
    head, _, rest = dotted.partition(".")
    module = aliases.get(head)
    return f"{module}.{rest}" if module and rest else dotted


def _from_imports(
    tree: ast.AST, deprecations: Marks
) -> Iterator[tuple[str, str, ast.AST, Deprecation]]:
    """``from module import name`` where ``name`` is deprecated."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            mark = deprecations.get((node.module, alias.name))
            if mark is not None:
                yield node.module, alias.name, node, mark


def _attribute_uses(
    tree: ast.AST, deprecations: Marks
) -> Iterator[tuple[str, str, ast.AST, Deprecation]]:
    """``module.Name`` where ``Name`` is deprecated and ``module`` is imported."""
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        module, _, name = _resolved(_dotted(node), aliases).rpartition(".")
        mark = deprecations.get((module, name))
        if module and name and mark is not None:
            yield module, name, node, mark


def deprecated_uses(
    tree: ast.AST, deprecations: Marks
) -> Iterator[tuple[str, str, ast.AST, Deprecation]]:
    """Every import in one parsed file that names a deprecated symbol."""
    yield from _from_imports(tree, deprecations)
    yield from _attribute_uses(tree, deprecations)
