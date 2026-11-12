"""A package must still export what its own modules import from it.

Turning ``adapters/qgis/processing.py`` into a package left ``components.py``
importing ``_qt_filter`` from the package, which the package did not re-export;
the only thing that noticed was a QGIS host, where that import sits on the file
picker's path. The check is static on purpose: it holds for every package in the
workspace, including the ones no pure test may import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Names a module binds at its own top level, whatever it does with them.
_BINDINGS = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Import,
    ast.ImportFrom,
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
)

ROOT = Path(__file__).resolve().parents[3]


def _sources() -> list[Path]:
    """Every module of every package in the workspace, ``src`` layouts included."""
    return sorted(ROOT.glob("packages/*/src/**/*.py"))


def _bound(tree: ast.Module) -> set[str]:
    """The names an ``__init__.py`` puts on its package namespace statically."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            names.update(
                target.id
                for target in ast.walk(node)
                if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _submodules(package: Path) -> set[str]:
    """What ``from package import name`` also reaches without an export: its files."""
    return {
        child.stem for child in package.iterdir() if child.suffix in {".py", ".pyi"}
    }


def _package_of(module: Path, level: int, name: str | None) -> Path | None:
    """The package a relative import names, or ``None`` when it names a module."""
    base = module.parent
    for _ in range(level - 1):
        base = base.parent
    for part in (name or "").split("."):
        if not part:
            continue
        base = base / part
    return base if base.is_dir() else None


def _imported_from_packages() -> list[tuple[str, str, str]]:
    """``(module, package, name)`` for every name a module imports from a package."""
    found: list[tuple[str, str, str]] = []
    for module in _sources():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            package = _package_of(module, node.level, node.module)
            if package is None:
                continue
            for alias in node.names:
                if alias.name != "*":
                    found.append(
                        (
                            str(module.relative_to(ROOT)),
                            str(package.relative_to(ROOT)),
                            alias.name,
                        )
                    )
    return found


def _star_targets(tree: ast.Module) -> list[str]:
    """Relative module names an ``__init__`` star-imports (``from ._x import *``)."""
    return [
        node.module or ""
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.level
        and any(alias.name == "*" for alias in node.names)
    ]


def _exports_for(path: Path) -> set[str]:
    """Bound names plus star-import expansion for one ``__init__.py``."""
    tree = ast.parse(path.read_text("utf-8"))
    names = _bound(tree) | _submodules(path.parent)
    for target in _star_targets(tree):
        candidate = path.parent / f"{target}.py"
        if candidate.exists():
            names |= _bound(ast.parse(candidate.read_text("utf-8")))
    return names


_IMPORTS = _imported_from_packages()
_EXPORTS = {
    str(path.parent.relative_to(ROOT)): _exports_for(path)
    for path in _sources()
    if path.name == "__init__.py"
}


def test_the_check_looks_at_real_imports() -> None:
    """A guard that found nothing would pass the rest of this module silently."""
    assert len(_IMPORTS) > 50
    assert _EXPORTS


@pytest.mark.parametrize(("module", "package", "name"), _IMPORTS)
def test_a_package_exports_what_its_modules_import_from_it(
    module: str, package: str, name: str
) -> None:
    assert name in _EXPORTS[package], (
        f"{module} imports {name!r} from {package}, which does not export it"
    )
