"""HOST001 / HOST003: a declared host set the project or this QGIS cannot honour.

Decision-52 point 1 makes ``[tool.qgis-sdk] hosts`` the one place a plugin says
which hosts it targets, and makes a declaration that only one host can satisfy a
finding rather than a surprise at load time.

``HOST001`` - a Desktop-only declaration in a plugin that does not declare the
Desktop host: ``@toolbar``/``@menu``/``@shortcut``, a ``Dialog``/``Dock``
surface, or a web view (``[tool.qgis-sdk.web]``). A server-only plugin loads
that module and has nowhere to put a window.
``HOST003`` (warning) - the plugin declares the server host, and the QGIS this
interpreter can see was built without QGIS Server, so ``qgis.server`` is
absent. Nothing is wrong with the project; the environment cannot run it
(decision-52 implementation note, 2026-10-30). It is a warning because a
developer machine without server bindings is normal while the deployment target
may well have them.
``HOST002`` - a server declaration on a plugin that does not declare the server
host: ``@server.filter``, ``@server.service`` or ``@server.access_control``. The
mirror of ``HOST001``, and it arrived with the declarations themselves
(TASK-80): a Desktop-only plugin that imports a module of server hooks has
nothing to load them.

Only the source and the environment are read (decision-8): the project is never
imported. The environment is inspected with :func:`importlib.util.find_spec`,
whose ``Path``/``glob`` answer needs no import of QGIS at all.
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from qgis_sdk.core.host import Host

from .diagnostics import Diagnostic
from .names import ModuleNames

if TYPE_CHECKING:  # imported by the caller: this module is imported by it
    from qgis_sdk_tools.project import ProjectConfig

__all__ = [
    "DESKTOP_BINDINGS",
    "SERVER_BINDINGS",
    "SURFACE_CLASSES",
    "check_declared_hosts",
    "check_hosts",
]

#: Decorators that need a window: the Desktop toolbar, its menus and shortcuts.
DESKTOP_BINDINGS = frozenset({"toolbar", "menu", "shortcut"})
#: ``qgis_sdk`` modules those decorators are imported from.
_BINDING_SOURCES = frozenset({"qgis_sdk", "qgis_sdk.bindings"})
#: Surface classes that only a GUI host can open.
SURFACE_CLASSES = frozenset({"Dialog", "Dock"})
_SURFACE_SOURCES = frozenset({"qgis_sdk.ui", "qgis_sdk.ui.surfaces"})
#: Decorators only QGIS Server calls: a filter, a service and an access hook.
SERVER_BINDINGS = frozenset({"filter", "service", "access_control"})
#: The only module they are imported from. `qgis_sdk` does not re-export them:
#: `filter` and `service` are common names, and a plugin that wants them says
#: `qgis_sdk.server` so a reader can see which host it is writing for.
_SERVER_SOURCES = frozenset({"qgis_sdk.server"})

_PYPROJECT = Path("pyproject.toml")


def check_hosts(
    source: str, *, path: Path, hosts: Sequence[str]
) -> Iterator[Diagnostic]:
    """Yield the ``HOST001``/``HOST002`` findings in ``source`` for ``hosts``.

    ``path`` is the root-relative path the diagnostics report. The two rules are
    independent: a project that declares neither host answers for both kinds of
    declaration, and one that declares the Desktop host still has to answer for a
    server hook. A file that does not parse is left to ``SYNTAX001``.
    """
    desktop = Host.DESKTOP.value in hosts
    server = Host.SERVER.value in hosts
    if desktop and server:
        return
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return
    names = ModuleNames(tree)
    if not desktop:
        yield from _desktop_declarations(tree, names, path, hosts)
    if not server:
        yield from _server_declarations(tree, names, path, hosts)


def _desktop_declarations(
    tree: ast.Module, names: ModuleNames, path: Path, hosts: Sequence[str]
) -> Iterator[Diagnostic]:
    """``HOST001``: a binding or surface that only a window can host."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                dotted = names.declared_as(decorator)
                if dotted is None:
                    continue
                module, _, attribute = dotted.rpartition(".")
                if module in _BINDING_SOURCES and attribute in DESKTOP_BINDINGS:
                    yield _desktop_finding(
                        path,
                        decorator.lineno,
                        decorator.col_offset + 1,
                        f"the `@{attribute}` binding on `{node.name}`",
                        hosts,
                    )
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                dotted = names.dotted(base)
                if dotted is None:
                    continue
                module, _, attribute = dotted.rpartition(".")
                if module in _SURFACE_SOURCES and attribute in SURFACE_CLASSES:
                    yield _desktop_finding(
                        path,
                        node.lineno,
                        node.col_offset + 1,
                        f"the `{node.name}` {attribute} surface",
                        hosts,
                    )
                    break


def _server_declarations(
    tree: ast.Module, names: ModuleNames, path: Path, hosts: Sequence[str]
) -> Iterator[Diagnostic]:
    """``HOST002``: a hook only QGIS Server calls, on a plugin without it."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            dotted = names.declared_as(decorator)
            if dotted is None:
                continue
            module, _, attribute = dotted.rpartition(".")
            if module in _SERVER_SOURCES and attribute in SERVER_BINDINGS:
                yield _server_declaration_finding(
                    path,
                    decorator.lineno,
                    decorator.col_offset + 1,
                    f"the `@server.{attribute}` hook on `{node.name}`",
                    hosts,
                )


def check_declared_hosts(config: ProjectConfig) -> Iterator[Diagnostic]:
    """Yield the findings that need the whole project: ``HOST001`` and ``HOST003``."""
    hosts = config.hosts
    if config.web is not None and Host.DESKTOP.value not in hosts:
        yield _desktop_finding(
            _PYPROJECT,
            0,
            0,
            "a web view (`[tool.qgis-sdk.web]`)",
            hosts,
        )
    if Host.SERVER.value in hosts and qgis_server_state() is False:
        yield _server_unavailable_finding()


def qgis_server_state() -> bool | None:
    """Whether the visible QGIS has server bindings, or ``None`` when unreadable.

    ``True`` when ``qgis.server`` is importable by this interpreter, ``False``
    when a QGIS is visible and its installation carries no server bindings, and
    ``None`` when no QGIS is visible at all - a pure test or a CI job that only
    runs ``check``. Only the installation directory is inspected, so QGIS is
    never imported here.
    """
    try:
        spec = importlib.util.find_spec("qgis")
    except (ImportError, ValueError):  # a broken installation is not a verdict
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        base = Path(location)
        if (base / "server" / "__init__.py").exists():
            return True
        if any(base.glob("_server*.so")) or any(base.glob("_server*.pyd")):
            return True
    return False


def _desktop_finding(
    path: Path, line: int, column: int, what: str, hosts: Sequence[str]
) -> Diagnostic:
    declared = ", ".join(hosts) or "none"
    return Diagnostic(
        rule="HOST001",
        path=path,
        line=line,
        column=column,
        message=(
            f"{what} needs the Desktop host, but `[tool.qgis-sdk] hosts` declares "
            f"{declared}"
        ),
        remediation=(
            "Add `desktop` to `[tool.qgis-sdk] hosts`, or keep the Desktop "
            "declaration in a module only the Desktop host loads (decision-52 "
            "point 1)."
        ),
    )


def _server_declaration_finding(
    path: Path, line: int, column: int, what: str, hosts: Sequence[str]
) -> Diagnostic:
    declared = ", ".join(hosts) or "none"
    return Diagnostic(
        rule="HOST002",
        path=path,
        line=line,
        column=column,
        message=(
            f"{what} needs the server host, but `[tool.qgis-sdk] hosts` declares "
            f"{declared}"
        ),
        remediation=(
            "Add `server` to `[tool.qgis-sdk] hosts`, or keep the server hook in "
            "a module only the server host loads (decision-52 point 1)."
        ),
    )


def _server_unavailable_finding() -> Diagnostic:
    return Diagnostic(
        rule="HOST003",
        path=_PYPROJECT,
        line=0,
        column=0,
        message=(
            "`[tool.qgis-sdk] hosts` declares `server`, but the QGIS visible to "
            "this interpreter was built without QGIS Server (no `qgis.server`)"
        ),
        remediation=(
            "A server plugin needs a QGIS built with `WITH_SERVER=ON` and "
            "bindings: `qgis-server` plus `python3-qgis` on Debian/Ubuntu, the "
            "official installers, or a source build. conda-forge builds QGIS "
            "without it, so `qgis-sdk test --target server` will skip here."
        ),
        severity="warning",
    )
