"""A scripted ``AppBackend``: the app host's lifecycle without Qt.

``qgis_sdk.app.AppSession`` decides the order a standalone app starts and stops
in, how long it waits for jobs and what it reports; this fake is what proves
that without a display, a ``QgsApplication`` or an event loop. It is the same
bargain ``FakeServerInterface`` makes for the server host, and it is what
``qgis-sdk run --once`` exercises for real on a machine with QGIS.

Everything the backend was asked to do is recorded, in order, in ``calls``:
``init``, ``build``, ``exec``, ``process_events``, ``quit``, ``exit``. A test
asserts the order and the counts - ``exit`` exactly once is a claim about a
count, not about a comment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.core import Host, NamedLoop, PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.core._application import QgisSdkPlugin

from .fakes import RecordingNotifications
from .jobs import FakeWorkers
from .ui import FakeUi

__all__ = ["FakeAppBackend", "FakeAppSurface", "FakeLoop"]


@dataclass
class FakeLoop:
    """A named loop a test can start, stop and inspect."""

    name: str = "job-pump"
    running: bool = False
    stops: int = 0

    def start(self) -> None:
        """Arm the loop, as a host does right after creating it."""
        self.running = True

    def stop(self) -> None:
        """Disarm it and count the call."""
        self.stops += 1
        self.running = False


@dataclass
class FakeAppSurface:
    """The context and UI one fake run got, plus what was done to them."""

    context: PluginContext
    gui: bool = False
    """Whether the run asked for a window."""
    title: str = ""
    """The title the run was built with."""
    loops: tuple[NamedLoop, ...] = ()
    runtime: PluginRuntime | None = None
    binds: int = 0
    closes: int = 0
    closer: Any = None
    """Called by :meth:`close`, so a test can watch the UI come down."""

    def bind(self, runtime: PluginRuntime) -> tuple[NamedLoop, ...]:
        """Record the runtime and start the loops, as the real surface does."""
        self.binds += 1
        self.runtime = runtime
        for loop in self.loops:
            start = getattr(loop, "start", None)
            if start is not None:
                start()
        return self.loops

    def close(self) -> None:
        """Record the teardown and run the test's own hook, if it set one."""
        self.closes += 1
        if self.closer is not None:
            self.closer()


@dataclass
class FakeAppBackend:
    """An ``AppBackend`` that does nothing Qt, and records everything asked."""

    host: Host = Host.APP
    """Which host the built context reports; ``APP`` unless a test wants a lie."""

    loops: tuple[NamedLoop, ...] = field(default_factory=lambda: (FakeLoop(),))
    """The loops every surface returns from ``bind``."""

    workers: FakeWorkers = field(default_factory=FakeWorkers)
    """The worker pool the context carries, so a job can be submitted."""

    exec_code: int = 0
    """What :meth:`exec` returns, as a process exit code."""

    init_error: BaseException | None = None
    """Raised by :meth:`init`, to prove a failed start still exits the toolkit."""

    build_error: BaseException | None = None
    """Raised by :meth:`build`, the same claim one step later."""

    surface_closer: Any = None
    """Called when a surface closes; see :attr:`FakeAppSurface.closer`."""

    notifications: RecordingNotifications | None = None
    """What the last built context records to; set by :meth:`build`."""

    calls: list[str] = field(default_factory=list)
    argv: tuple[str, ...] = ()
    surfaces: list[FakeAppSurface] = field(default_factory=list)
    exits: int = 0

    def init(self, argv: Sequence[str]) -> None:
        self.calls.append("init")
        self.argv = tuple(argv)
        if self.init_error is not None:
            raise self.init_error

    def build(self, app: QgisSdkPlugin, *, gui: bool, title: str) -> FakeAppSurface:
        self.calls.append("build")
        if self.build_error is not None:
            raise self.build_error
        scope = ResourceScope()
        self.notifications = RecordingNotifications(scope)
        context = PluginContext(
            notifications=self.notifications,
            scope=scope,
            host=self.host,
            workers=self.workers,
        )
        if gui:
            context = context.with_services(ui=FakeUi(scope, app=app))
        surface = FakeAppSurface(
            context=context,
            gui=gui,
            title=title,
            loops=self.loops,
            closer=self.surface_closer,
        )
        self.surfaces.append(surface)
        return surface

    def exec(self) -> int:
        self.calls.append("exec")
        return self.exec_code

    def process_events(self) -> None:
        self.calls.append("process_events")

    def quit(self) -> None:
        self.calls.append("quit")

    def exit(self) -> None:
        self.calls.append("exit")
        self.exits += 1

    @property
    def surface(self) -> FakeAppSurface:
        """The one surface this backend built, for the test that asserts on it."""
        return self.surfaces[-1]
