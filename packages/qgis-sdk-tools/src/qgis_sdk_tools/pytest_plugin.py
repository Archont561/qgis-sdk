"""The pytest plugin ``qgis-sdk test`` loads with ``-p qgis_sdk_tools.pytest_plugin``.

It is small on purpose, and every part of it also works under a direct
``pytest`` (decision-7: the command is a thin runner, never the only way):

* the ``qgis``, ``desktop`` and ``server`` markers, so a ``--strict-markers``
  project needs no ``conftest`` to name its native tests;
* the **pure guard**: when the command set ``QGIS_SDK_TEST_TARGET=pure``, an
  import of ``qgis``, PyQt or PySide fails at once with the way out. Markers
  cannot stop a module-level import from running at collection time, so the
  guard is what makes "pure collection avoids native imports" true;
* the **skip gate**: in the ``qgis``, ``desktop`` and ``server`` targets a
  session in which every test skipped exits ``1``. A requested native gate
  does not pass by skipping;
* the **bindings gate**: the ``server`` target refuses the session when
  ``qgis.server`` is not importable, naming the build that has it. A QGIS
  from conda-forge cannot run that target, and a skip would read as a pass;
* two fixtures: ``qgis_app`` (a headless ``QgsApplication`` for the ``qgis``
  target, the running one in ``desktop``) and ``qgis_iface`` (Desktop only).
  Outside their target they fail and name the command to run;
* a third, ``ui_snapshot``: capture a surface and compare it with the one the
  project approved under ``tests/__snapshots__`` (decision-51). It is created
  and verified without QGIS - the surface it is given is what needs QGIS - so a
  test marked ``qgis`` is where it is usually used;
* in the ``desktop`` target, top-level packages found on ``QGIS_PLUGINPATH``
  win over ``sys.path``, so ``import <plugin>`` is the package QGIS loaded -
  the generated host package of decision-43, which carries ``classFactory`` -
  rather than the bare source package pytest puts first.

Without ``QGIS_SDK_TEST_TARGET`` - a developer typing ``pytest`` - the guard
and the gate are off and ``qgis_app`` skips when PyQGIS is not importable,
which is pytest's own convention for an optional runtime.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import os
import sys
from collections.abc import Iterator, Sequence
from typing import Any, Final

import pytest
from qgis_sdk.environment import TEST_TARGET_ENV as TARGET_ENV

__all__ = ["NATIVE_TARGETS", "TARGETS", "TARGET_ENV"]

TARGETS: Final = ("pure", "qgis", "desktop", "server", "web")
NATIVE_TARGETS: Final = frozenset({"qgis", "desktop", "server"})
NATIVE_ROOTS: Final = frozenset({"qgis", "PyQt5", "PyQt6", "PySide2", "PySide6"})

MARKERS: Final = (
    "qgis: needs PyQGIS and a QgsApplication; run with `qgis-sdk test --target qgis`",
    (
        "desktop: needs a running QGIS Desktop (iface); "
        "run with `qgis-sdk test --target desktop`"
    ),
    (
        "server: needs QGIS Server bindings (qgis.server); "
        "run with `qgis-sdk test --target server`"
    ),
)

SERVER_BUILD_HELP: Final = (
    "the QGIS at this prefix was built without server support (`import "
    "qgis.server` failed: {error}). The server target needs QGIS configured "
    "with -DWITH_SERVER=ON -DWITH_BINDINGS=ON; conda-forge builds it off, so "
    "install `qgis-server` and `python3-qgis` from the qgis.org or Debian "
    "repositories, or point --qgis-prefix at a build that has them "
    "(decision-52)."
)


def _target() -> str | None:
    return os.environ.get(TARGET_ENV) or None


class _PureGuard(importlib.abc.MetaPathFinder):
    """Refuse native imports in the pure target, with the remedy in the message."""

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname.split(".")[0] in NATIVE_ROOTS:
            raise ImportError(
                f"`{fullname}` is a native module and this is the pure target: "
                "import it inside a test marked `qgis` or `desktop`, and run those "
                "with `qgis-sdk test --target qgis` (or `--target desktop`)"
            )
        return None


class _HostFirst(importlib.abc.MetaPathFinder):
    """Resolve top-level packages from QGIS's plugin directories before ``sys.path``.

    pytest's ``pythonpath`` and conftest loading both put the project root at
    the front of ``sys.path``; a path entry cannot win against that, a finder
    ahead of ``PathFinder`` can. Submodules are untouched: the host package
    extends its own ``__path__`` to the sources, so ``<plugin>.plugin`` is
    the author's module either way.
    """

    def __init__(self, roots: Sequence[str]) -> None:
        self._roots = list(roots)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if "." in fullname:
            return None
        return importlib.machinery.PathFinder.find_spec(fullname, self._roots)


def pytest_load_initial_conftests(early_config: pytest.Config) -> None:
    """Desktop target: the plugin is importable the way the running QGIS loaded it.

    Installed before the first conftest imports anything, so every import of
    the plugin package in the session resolves to the host package.
    """
    if _target() != "desktop":
        return
    roots = [p for p in os.environ.get("QGIS_PLUGINPATH", "").split(os.pathsep) if p]
    if roots and not any(isinstance(f, _HostFirst) for f in sys.meta_path):
        sys.meta_path.insert(0, _HostFirst(roots))


def configured_bindings_error(target: str | None) -> str | None:
    """Why ``target`` cannot run here, or ``None``; the server target's one check.

    Only the server target has a binding of its own: ``qgis`` and ``desktop``
    need PyQGIS, which the session fixture already reports when it is missing,
    while a QGIS built without ``WITH_SERVER`` imports ``qgis.core`` happily and
    has no ``qgis.server`` at all.
    """
    if target != "server":
        return None
    try:
        from qgis import server  # noqa: F401
    except ImportError as error:
        return SERVER_BUILD_HELP.format(error=error)
    return None


def pytest_configure(config: pytest.Config) -> None:
    for marker in MARKERS:
        config.addinivalue_line("markers", marker)
    target = _target()
    if target == "pure" and not any(isinstance(f, _PureGuard) for f in sys.meta_path):
        sys.meta_path.insert(0, _PureGuard())
    missing = configured_bindings_error(target)
    if missing is not None:
        pytest.exit(missing, returncode=1)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    target = _target()
    if target not in NATIVE_TARGETS or exitstatus != 0:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - only without a terminal reporter
        return
    ran = sum(len(reporter.stats.get(key, ())) for key in ("passed", "xfailed"))
    skipped = len(reporter.stats.get("skipped", ()))
    if ran == 0 and skipped > 0:
        reporter.write_line(
            f"qgis-sdk test: every test of the {target} target was skipped; "
            "a native gate does not pass by skipping",
            red=True,
        )
        session.exitstatus = 1


@pytest.fixture(scope="session")
def qgis_app() -> Iterator[Any]:
    """A ``QgsApplication``: started here for ``qgis``, the Desktop's own in ``desktop``."""
    target = _target()
    if target is not None and target not in NATIVE_TARGETS:
        pytest.fail(
            "qgis_app needs PyQGIS; mark the test `qgis` and run "
            "`qgis-sdk test --target qgis`",
            pytrace=False,
        )
    try:
        from qgis.core import QgsApplication
    except ImportError as error:
        message = (
            f"PyQGIS is not importable here ({error}); run `qgis-sdk test --target "
            "qgis`, and give it --qgis-prefix if it cannot find QGIS"
        )
        if target is None:
            pytest.skip(message)
        pytest.fail(message, pytrace=False)
    existing = QgsApplication.instance()
    if existing is not None:
        yield existing
        return
    from qgis_sdk_tools.devtools import wants_headless

    if wants_headless(os.environ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    app = QgsApplication([b"qgis-sdk-test"], True)
    app.initQgis()
    try:
        yield app
    finally:
        app.exitQgis()


@pytest.fixture
def ui_snapshot(request: pytest.FixtureRequest) -> Iterator[Any]:
    """Capture a surface and compare it with the project's approval.

    ``ui_snapshot(surface)`` returns the capture with its difference from
    ``<test module>/__snapshots__/<surface>.json``; after the test, an
    unapproved or structurally changed surface fails it with the readable diff
    (decision-51 point 5). Call ``.approve()`` on what it returned to write the
    JSON and the PNG - that is the one way an approval changes. The surface is
    a ``SurfaceCapture`` a host made (only the surfaces the plugin opened, so
    never another plugin's window) or a widget this test built.
    """
    from qgis_sdk_tools.snapshots import SNAPSHOTS_DIRECTORY, Snapshots

    snapshots = Snapshots(request.path.parent / SNAPSHOTS_DIRECTORY)
    yield snapshots
    snapshots.verify()


@pytest.fixture(scope="session")
def qgis_iface(request: pytest.FixtureRequest) -> Any:
    """The Desktop ``iface``; only the ``desktop`` target has one."""
    if _target() != "desktop":
        pytest.fail(
            "qgis_iface exists only inside QGIS Desktop; mark the test `desktop` "
            "and run `qgis-sdk test --target desktop`",
            pytrace=False,
        )
    request.getfixturevalue("qgis_app")
    import qgis.utils

    return qgis.utils.iface
