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
from typing import Any

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


def run(
    app: QgisSdkPlugin,
    *,
    gui: bool = False,
    argv: Sequence[str] | None = None,
    grace: float = GRACE_SECONDS,
    once: bool = False,
    backend: AppBackend | None = None,
    title: str | None = None,
) -> int:
    """Run ``app`` as a standalone PyQGIS application; return the exit code.

    ``argv`` is what the toolkit sees (``sys.argv[1:]`` from a launcher);
    ``gui`` opens the window and with it ``ctx.ui`` and the Desktop-style
    bindings; ``grace`` bounds the wait for running jobs at shutdown;
    ``once`` starts the app, delivers what is already queued and stops instead
    of running the event loop (``qgis-sdk run --once``). ``backend`` is the
    toolkit seam: left out, the Qt one in :mod:`qgis_sdk.adapters.app` is built,
    which is the only import here that needs QGIS.
    """
    global _running
    if _running is not None:
        raise QgisSdkAppError(
            f"{_running!r} is still running; a process hosts one application at "
            "a time (a standalone app is the top level, not a plugin inside one)"
        )
    chosen = backend if backend is not None else _qt_backend()
    session = AppSession(
        app,
        backend=chosen,
        gui=gui,
        argv=argv,
        grace=grace,
        title=title,
    )
    _running = session
    try:
        return session.run(once=once)
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
    try:
        options = parse_argv(argv)
    except QgisSdkAppError as error:
        print(f"qgis-sdk app: {error}", file=sys.stderr)
        return 2
    try:
        return run(
            app,
            gui=options.gui,
            argv=options.argv,
            grace=options.grace,
            once=options.once,
            backend=backend,
            title=options.title,
        )
    except QgisSdkAppError as error:
        # A launcher has no traceback to show: the refusal is the whole message.
        print(f"qgis-sdk app: {error}", file=sys.stderr)
        return 2


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
