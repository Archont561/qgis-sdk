"""Run one plugin as a standalone PyQGIS application instead of a QGIS plugin.

``qgis_sdk.app.run(app)`` owns ``QgsApplication``, builds a context with no
``iface``, starts the plugin's runtime, and - with ``gui=True`` - opens a window
with a map canvas the plugin's ``@toolbar``/``@menu`` bindings and its
``Dialog``/``Dock`` surfaces attach to. It is the third host of decision-52, and
the same author class runs on all three: what changes is what the host offers,
and a capability this one does not have refuses by name like anywhere else.

    from qgis_sdk.app import run

    if __name__ == "__main__":
        raise SystemExit(run(app, gui=True))

A *launcher* - ``python -m <plugin>``, the console script ``build --target app``
installs, or ``qgis-sdk run`` - has argv to read, so it calls :func:`main`
instead: it parses ``--headless``, ``--once``, ``--grace`` and ``--title``
(:mod:`qgis_sdk.app._options`), passes everything after ``--`` to the toolkit,
and returns the exit code the process should use.

``ctx.host`` is ``app`` either way, ``ctx.desktop`` refuses by name (there is no
``QgisInterface`` to wrap), and ``ctx.ui`` exists only with ``gui=True`` - a
headless app can run jobs and read the project, but has nowhere to open a
dialog. The bridge is unchanged: a page a ``gui=True`` app shows goes through the
same host services, the same grants and the same WebChannel transport as in
QGIS Desktop.

Shutdown is bounded (decision-69 point 2): ``run`` stops the loops it named,
waits ``grace`` seconds for running jobs, names and cancels what is left, and
calls ``exitQgis`` exactly once. ``qgis_sdk.testing.FakeAppBackend`` drives the
same session with no Qt at all.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypedDict, Unpack

from qgis_sdk.core._application import QgisSdkPlugin
from qgis_sdk.core.host import Host

from ._backend import AppBackend, AppSurface
from ._options import AppOptions, parse_argv
from ._session import (
    DRAIN_INTERVAL,
    GRACE_SECONDS,
    AppSession,
    QgisSdkAppError,
    ShutdownReport,
)


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


def _cc_main_p1(_s):
    try:
        _s.options = parse_argv(_s.argv)
    except QgisSdkAppError as error:
        _s.error = error
        print(f"qgis-sdk app: {_s.error}", file=sys.stderr)
        return _CcReturn(2)


def _cc_main_p2(_s):
    try:
        return _CcReturn(
            run(
                _s.app,
                gui=_s.options.gui,
                argv=_s.options.argv,
                grace=_s.options.grace,
                once=_s.options.once,
                backend=_s.backend,
                title=_s.options.title,
            )
        )
    except QgisSdkAppError as error:
        _s.error = error
        # A launcher has no traceback to show: the refusal is the whole message.
        print(f"qgis-sdk app: {_s.error}", file=sys.stderr)
        return _CcReturn(2)


__all__ = [
    "DRAIN_INTERVAL",
    "GRACE_SECONDS",
    "AppBackend",
    "AppOptions",
    "AppSession",
    "AppSurface",
    "Host",
    "QgisSdkAppError",
    "ShutdownReport",
    "main",
    "parse_argv",
    "quit",
    "run",
]

#: The host that is running right now, so ``quit()`` can reach its backend.
_running: AppSession | None = None


def run(app: QgisSdkPlugin, **options: Unpack[_RunOptions1]) -> int:
    "Run ``app`` as a standalone PyQGIS application; return the exit code.\n\n    ``argv`` is what the toolkit sees (``sys.argv[1:]`` from a launcher);\n    ``gui`` opens the window and with it ``ctx.ui`` and the Desktop-style\n    bindings; ``grace`` bounds the wait for running jobs at shutdown;\n    ``once`` starts the app, delivers what is already queued and stops instead\n    of running the event loop (``qgis-sdk run --once``). ``backend`` is the\n    toolkit seam: left out, the Qt one in :mod:`qgis_sdk.adapters.app` is built,\n    which is the only import here that needs QGIS.\n"
    values = _RunValues1(**options)
    global _running
    if _running is not None:
        raise QgisSdkAppError(
            f"{_running!r} is still running; a process hosts one application at "
            "a time (a standalone app is the top level, not a plugin inside one)"
        )
    chosen = values.backend if values.backend is not None else _qt_backend()
    session = AppSession(
        app,
        backend=chosen,
        gui=values.gui,
        argv=values.argv,
        grace=values.grace,
        title=values.title,
    )
    _running = session
    try:
        return session.run(once=values.once)
    finally:
        _running = None


def main(
    app: QgisSdkPlugin,
    argv: Sequence[str] | None = None,
    *,
    backend: AppBackend | None = None,
) -> int:
    """Run ``app`` with the flags a launcher passes; return the exit code.

    ``argv`` is ``sys.argv[1:]`` when left out. A flag this module cannot read
    is reported on stderr and answered with exit code 2 rather than starting a
    window with settings nobody asked for - a double-clicked console script has
    no traceback to show. Everything the SDK does not recognise goes to the
    toolkit, so ``-platform offscreen`` works from a launcher too.
    """
    _s = _CcState(**locals())
    for _p in (_cc_main_p1, _cc_main_p2):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def quit() -> None:
    """Ask the running application to leave its event loop.

    The one hook a plugin needs to end a headless app: a job that finished, a
    batch that has nothing left to do. Called with no app running it refuses by
    name rather than reaching for a Qt singleton that may belong to someone else.
    """
    if _running is None:
        raise QgisSdkAppError(
            "no application host is running; `qgis_sdk.app.quit()` is for a "
            "plugin inside `qgis_sdk.app.run()`, not for a QGIS Desktop session"
        )
    _running.quit()


def _qt_backend() -> AppBackend:
    """The PyQGIS backend, imported only when an app is actually started."""
    from qgis_sdk.adapters.app import QtAppBackend

    return QtAppBackend()


def current() -> Any:
    """The session ``run()`` is driving, for tests and for a host's own tooling."""
    return _running


class _RunOptions1(TypedDict, total=False):
    gui: bool
    argv: Sequence[str] | None
    grace: float
    once: bool
    backend: AppBackend | None
    title: str | None


@dataclass(frozen=True, slots=True)
class _RunValues1:
    gui: bool = False
    argv: Sequence[str] | None = None
    grace: float = GRACE_SECONDS
    once: bool = False
    backend: AppBackend | None = None
    title: str | None = None
