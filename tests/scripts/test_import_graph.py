"""The import graph the QGIS-free suite cannot see.

The native adapters under ``qgis_sdk.adapters.qgis`` only import where PyQGIS
exists, so nothing a developer runs locally ever loads them. Two failures hide
there for exactly that reason:

* a chunk importing a name its sibling moved away - ``ImportError: cannot import
  name X from partially initialized module`` or a plain ``ImportError`` - which
  turns a CI step into "exit code 1" on a runner;
* two chunks importing each other, which is the same failure wearing a
  different message.

Both are properties of the *source*, not of a running interpreter, so both are
read from the AST here: the module-body imports are the ones that execute on
``import``, which is what makes a cycle or a missing name fatal, while
``if TYPE_CHECKING:`` imports bind nothing at runtime and are ignored.

A name imported at module scope must be bound at module scope in the target:
a function-local import there, or a ``TYPE_CHECKING`` one, does not put it on
the module, and reading it off the module is what raises.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = tuple(sorted((ROOT / "packages").glob("*/src")))
AUTOMATION = ROOT / "automation"


def _module_name(path: Path, root: Path) -> str:
    """The dotted name ``path`` is importable as, from ``root``."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _modules() -> dict[str, Path]:
    """Every importable module under the shipped roots, by dotted name."""
    found = {
        _module_name(path, root): path
        for root in PACKAGES
        for path in root.rglob("*.py")
    }
    for path in AUTOMATION.rglob("*.py"):
        found[f"automation.{_module_name(path, AUTOMATION)}"] = path
    return found


def _walk(statements: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield the statements a module runs on import, minus the guarded ones."""
    for node in statements:
        if isinstance(node, ast.If):
            type_only = any(
                isinstance(sub, ast.Name) and sub.id == "TYPE_CHECKING"
                for sub in ast.walk(node.test)
            )
            yield from _walk(node.orelse if type_only else node.body)
            if not type_only:
                yield from _walk(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _walk(node.body)
            for handler in node.handlers:
                yield from _walk(handler.body)
            yield from _walk(node.orelse)
            yield from _walk(node.finalbody)
        elif isinstance(node, ast.With | ast.AsyncWith):
            yield from _walk(node.body)
        else:
            yield node


def _imports(path: Path) -> list[ast.Import | ast.ImportFrom]:
    return [
        node
        for node in _walk(ast.parse(path.read_text(encoding="utf-8")).body)
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]


def _binds(path: Path) -> set[str]:
    """Every name the module puts on itself when it is imported."""
    names = {"__all__", "__doc__", "__name__", "__future__"}
    for node in _walk(ast.parse(path.read_text(encoding="utf-8")).body):
        names.update(_bound_name(node))
    return names


def _bound_name(node: ast.stmt) -> set[str]:
    """The names one statement binds, or nothing when it binds none."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return {node.name}
    if isinstance(node, ast.Import | ast.ImportFrom):
        return _alias_names(node)
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def _alias_names(node: ast.Import | ast.ImportFrom) -> set[str]:
    dotted = isinstance(node, ast.Import)
    return {
        alias.asname or (alias.name.split(".")[0] if dotted else alias.name)
        for alias in node.names
    }


def _is_open(path: Path) -> bool:
    """A star import or a module ``__getattr__`` binds names nobody can read."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        (isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names))
        or (isinstance(node, ast.FunctionDef) and node.name == "__getattr__")
        for node in ast.walk(tree)
    )


def _target(name: str, node: ast.ImportFrom, path: Path) -> str:
    """The dotted module ``node`` imports from, resolved against ``name``."""
    if not node.level:
        return node.module or ""
    package = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
    package = package[: len(package) - (node.level - 1)]
    prefix = ".".join(package)
    return f"{prefix}.{node.module}" if node.module else prefix


MODULES = _modules()
OPEN = {name for name, path in MODULES.items() if _is_open(path)}
BOUND = {name: _binds(path) for name, path in MODULES.items()}


def _edges(name: str, path: Path) -> set[str]:
    internal: set[str] = set()
    for node in _imports(path):
        target = _target(name, node, path) if isinstance(node, ast.ImportFrom) else ""
        internal.update(_imported_modules(target, node, name, path) - {name})
    return internal


def _imported_modules(
    target: str, node: ast.Import | ast.ImportFrom, name: str, path: Path
) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names if alias.name in MODULES}
    found = {
        f"{target}.{alias.name}"
        for alias in node.names
        if f"{target}.{alias.name}" in MODULES
    }
    return found | {target} if target in MODULES else found


GRAPH = {name: _edges(name, path) for name, path in MODULES.items()}


class _Components:
    """Tarjan's strongly connected components, over the module graph.

    Only components with more than one module are interesting: a module that
    imports itself is not a cycle the interpreter can trip over.
    """

    def __init__(self, graph: dict[str, set[str]]) -> None:
        self.graph = graph
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.stack: list[str] = []
        self.on_stack: set[str] = set()
        self.found: list[list[str]] = []

    def cycles(self) -> list[list[str]]:
        for node in self.graph:
            if node not in self.index:
                self._visit(node)
        return [component for component in self.found if len(component) > 1]

    def _visit(self, node: str) -> None:
        self.index[node] = self.low[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        for edge in self.graph[node]:
            if edge not in self.index:
                self._visit(edge)
                self.low[node] = min(self.low[node], self.low[edge])
            elif edge in self.on_stack:
                self.low[node] = min(self.low[node], self.index[edge])
        if self.low[node] == self.index[node]:
            self._drain(node)

    def _drain(self, node: str) -> None:
        component: list[str] = []
        while True:
            member = self.stack.pop()
            self.on_stack.discard(member)
            component.append(member)
            if member == node:
                break
        self.found.append(component)


def _cycles() -> list[list[str]]:
    """The module-body import cycles, as the modules involved in each one."""
    return _Components(GRAPH).cycles()


def _unresolved() -> list[str]:
    missing: list[str] = []
    for name, path in MODULES.items():
        for node in _imports(path):
            if isinstance(node, ast.ImportFrom):
                missing.extend(_missing_names(name, path, node))
    return missing


def _missing_names(name: str, path: Path, node: ast.ImportFrom) -> list[str]:
    target = _target(name, node, path)
    if target not in MODULES or target in OPEN:
        return []
    prefix = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    return [
        f"{prefix}:{node.lineno} imports {alias.name} from {target}, which does not bind it"
        for alias in node.names
        if alias.name != "*"
        and alias.name not in BOUND[target]
        and f"{target}.{alias.name}" not in MODULES
    ]


PREFIXES = ("qgis_sdk.", "qgis_sdk_tools.", "automation.")


def _unresolved_modules() -> list[str]:
    """Relative and in-tree imports whose target module is not there.

    Read from every import, not only the module-body ones: a function-local
    ``from .bootstrap import say`` is still a ``ModuleNotFoundError`` the first
    time that function runs, and moving a file into a package of its own is
    exactly what turns ``.bootstrap`` into ``..bootstrap``.
    """
    missing: list[str] = []
    for name, path in MODULES.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        missing.extend(_missing_modules(name, path, tree))
    return missing


def _missing_modules(name: str, path: Path, tree: ast.Module) -> list[str]:
    wanted = {
        _target(name, node, path) if node.level else (node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    return [
        f"{path}:{name} imports the missing module {target}"
        for target in sorted(wanted)
        if _is_missing(target)
    ]


def _is_missing(target: str) -> bool:
    if target in MODULES or target in {"", "__future__"}:
        return False
    if not target.startswith(PREFIXES):
        return False
    return not any(f"{target}.{module}" in MODULES for module in _children(target))


def _children(target: str) -> set[str]:
    return {
        module[len(target) + 1 :].split(".")[0]
        for module in MODULES
        if module.startswith(f"{target}.")
    }


def test_every_imported_module_exists() -> None:
    """A relative import that resolves outside the package is a missing module."""
    assert _unresolved_modules() == [], "\n".join(_unresolved_modules())


def test_no_module_body_import_cycle() -> None:
    """Two modules importing each other fail whichever one is imported first."""
    assert _cycles() == [], f"import-time cycles: {_cycles()}"


def test_every_imported_name_is_bound_where_it_is_imported() -> None:
    """A module-scope import of a name the target does not bind is an ImportError."""
    assert _unresolved() == [], "\n".join(_unresolved())
