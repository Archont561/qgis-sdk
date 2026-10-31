"""One standalone PyQGIS application: start the plugin, loop, and stop in bounds.

``qgis_sdk.app.run(PluginClass, gui=...)`` is this file plus a backend. The order
is the whole design (decision-52 point 3, decision-69 points 2 and 4):

1. the backend creates and initialises ``QgsApplication``;
2. the backend builds a *surface* - a window with a map canvas when ``gui``, a
   bare context otherwise - and the context it carries has ``ctx.host == app``;
3. the runtime starts the plugin, and the surface places its bindings and starts
   its loops, which are recorded here by name;
4. the event loop runs until the app quits;
5. shutdown stops every recorded loop, waits for running jobs up to ``grace``
   seconds, names and cancels whatever is left, closes the UI, unloads the
   runtime, and calls ``exitQgis`` exactly once.

Nothing in this module imports Qt, and nothing here assumes a display: the
session is driven in the pure tests by ``qgis_sdk.testing.FakeAppBackend``, and
the Qt backend in ``qgis_sdk.adapters.app`` is the only place a window exists.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from qgis_sdk.core import (
    Host,
    LoopRegistry,
    LoopState,
    PluginContext,
    PluginRuntime,
)
from qgis_sdk.core._application import QgisSdkPlugin
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import QgisSdkAppError

from ._backend import AppBackend, AppSurface

__all__ = [
    "DRAIN_INTERVAL",
    "GRACE_SECONDS",
    "AppSession",
    "QgisSdkAppError",
    "ShutdownReport",
]

#: How long shutdown waits for a running job before naming and abandoning it
#: (decision-69 point 2). Fifteen seconds is long enough for a job that is
#: finishing a file and short enough that a stuck one cannot hold a quit.
GRACE_SECONDS = 15.0
#: How often the bounded wait ticks the job service while it waits.
DRAIN_INTERVAL = 0.02


@dataclass(frozen=True, slots=True)
class ShutdownReport:
    """What shutting one app down stopped, drained and abandoned.

    ``stopped`` names every background loop that was still running when the
    shutdown began, ``loops`` is the state each one reached, ``drained`` the
    jobs that finished inside the grace window and ``abandoned`` the ones that
    did not - each of those was asked to stop, is reported as cancelled, and no
    callback for it runs afterwards (decision-69 points 2 and 4).
    """

    stopped: tuple[str, ...]
    loops: tuple[LoopState, ...]
    drained: tuple[str, ...]
    abandoned: tuple[str, ...]
    grace_seconds: float
    elapsed: float
    exited: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "stopped_loops": list(self.stopped),
            "loops": [
                {"name": state.name, "running": state.running} for state in self.loops
            ],
            "drained_jobs": list(self.drained),
            "abandoned_jobs": list(self.abandoned),
            "grace_seconds": self.grace_seconds,
            "elapsed_seconds": round(self.elapsed, 6),
            "exited": self.exited,
        }

    def summary(self) -> str:
        """One line for a terminal: what was stopped and what was abandoned."""
        parts: list[str] = []
        if self.stopped:
            parts.append(
                f"stopped {_plural(len(self.stopped), 'loop')}: "
                + ", ".join(self.stopped)
            )
        else:
            parts.append("no background loops were running")
        if self.drained:
            parts.append(f"drained {_plural(len(self.drained), 'job')}")
        if self.abandoned:
            parts.append(
                f"abandoned {_plural(len(self.abandoned), 'job')} after "
                f"{self.grace_seconds:g}s: " + ", ".join(self.abandoned)
            )
        return "; ".join(parts)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


class AppSession:
    """Start one plugin under an application host, and stop it in bounds.

    The object exists so the lifecycle is testable without an event loop:
    :meth:`start` and :meth:`stop` are the two halves ``run()`` performs around
    ``exec()``, and the native tests drive them directly - the same shape
    ``ServerHost`` has for the server. ``gui`` decides only what the backend
    builds; ``ctx.host`` is ``app`` either way.
    """

    def __init__(
        self,
        app: QgisSdkPlugin,
        *,
        backend: AppBackend,
        gui: bool = False,
        argv: Sequence[str] | None = None,
        grace: float = GRACE_SECONDS,
        title: str | None = None,
        say: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(app, QgisSdkPlugin):
            raise QgisSdkDeclarationError("AppSession requires a QgisSdkPlugin")
        if grace < 0:
            raise QgisSdkAppError(f"grace must not be negative, got {grace!r}")
        description = app.describe()
        self._app = app
        self._app_id = description.id
        self._backend = backend
        self._gui = bool(gui)
        self._argv = tuple(argv or ())
        self._grace = float(grace)
        self._title = title or description.title
        self._say = say if say is not None else (lambda _message: None)
        self._clock = clock
        self._pause = pause
        self._loops = LoopRegistry()
        self._surface: AppSurface | None = None
        self._runtime: PluginRuntime | None = None
        self._started = False
        self._exited = False
        self._report: ShutdownReport | None = None

    # -- what a host reads -------------------------------------------------------------

    @property
    def gui(self) -> bool:
        """Whether this session was asked for a window."""
        return self._gui

    @property
    def runtime(self) -> PluginRuntime | None:
        """The plugin runtime, once :meth:`start` built it."""
        return self._runtime

    @property
    def context(self) -> PluginContext | None:
        """The context the plugin's hooks, bindings and actions read."""
        return None if self._runtime is None else self._runtime.context

    @property
    def loops(self) -> LoopRegistry:
        """The loops the surface started, by name."""
        return self._loops

    @property
    def report(self) -> ShutdownReport | None:
        """What shutdown stopped and abandoned, once it happened."""
        return self._report

    # -- lifecycle ---------------------------------------------------------------------

    def start(self) -> PluginRuntime:
        """Initialise the toolkit, build the context, start the plugin.

        A failure anywhere past ``init`` still tears the application down, so a
        caller never inherits a half-initialised ``QgsApplication`` it cannot
        use. The exception the failure caused is the one that propagates.
        """
        if self._started:
            raise QgisSdkAppError(
                f"{self._title}: this app session already started; call `stop` "
                "and build a new one"
            )
        self._backend.init(self._argv, gui=self._gui)
        try:
            surface = self._backend.build(self._app, gui=self._gui, title=self._title)
            self._surface = surface
            host = surface.context.host
            if host is not Host.APP:
                raise QgisSdkAppError(
                    f"{self._title}: the app host reported {host.value!r} as its "
                    "host; a context built for this host says 'app'"
                )
            runtime = PluginRuntime(self._app, surface.context)
            runtime.start()
            self._runtime = runtime
            for loop in surface.bind(runtime):
                self._loops.add(loop)
        except BaseException:
            self._release()
            raise
        self._started = True
        self._say(
            f"app: {self._app_id} running"
            + (" with a window" if self._gui else " headless")
        )
        return self._runtime

    def run(self, *, once: bool = False) -> int:
        """Start, spin the event loop, stop; return the process exit code.

        ``once`` delivers what is already queued and returns instead of waiting
        for someone to close the window - what ``qgis-sdk run --once`` does, and
        the way a script proves an app host starts and stops cleanly.
        """
        code = 0
        try:
            self.start()
            code = 0 if once else int(self._backend.exec())
            if once:
                self._backend.process_events()
        finally:
            self.stop()
        return code

    def quit(self) -> None:
        """Ask the app to leave its event loop; a no-op before the loop runs."""
        self._backend.quit()

    def stop(self) -> ShutdownReport:
        """Stop in the documented order, inside the documented bound."""
        if self._report is not None:
            return self._report
        began = self._clock()
        running = tuple(
            state.name for state in self._loops.inventory() if state.running
        )
        loops = self._loops.stop_all()
        self._say(self._loops_line(running))
        drained, abandoned = self._drain_jobs()
        for name in abandoned:
            self._say(
                f"app: abandoning job {name} after {self._grace:g}s; it is "
                "reported as cancelled and runs no callback"
            )
        self._release()
        self._report = ShutdownReport(
            stopped=running,
            loops=loops,
            drained=drained,
            abandoned=abandoned,
            grace_seconds=self._grace,
            elapsed=max(self._clock() - began, 0.0),
            exited=self._exited,
        )
        self._say(f"app: stopped; {self._report.summary()}")
        return self._report

    # -- shutdown pieces ---------------------------------------------------------------

    def _drain_jobs(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Wait for running jobs up to ``grace``; return drained, then abandoned.

        The wait ticks the plugin's job service - the same call the pump makes -
        so a job that finishes inside the window still delivers, and a job that
        does not is asked to stop here. Asking is what makes the verdict
        ``cancelled`` once the scope closes below: a job nobody asked to stop
        settles as ``failed`` with a closed-scope error, which is a lie about
        what happened.
        """
        runtime = self._runtime
        service = None if runtime is None else runtime.jobs
        if service is None:
            return (), ()
        active = tuple(service.active)
        if not active:
            return (), ()
        names = tuple(handle.id for handle in active)
        deadline = self._clock() + self._grace
        while service.active and self._clock() < deadline:
            service.tick()
            if not service.active:
                break
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            self._pause(min(DRAIN_INTERVAL, remaining))
        still: tuple[str, ...] = tuple(handle.id for handle in service.active)
        for handle in service.active:
            handle.cancel()
        drained = tuple(name for name in names if name not in still)
        return drained, still

    def _release(self) -> None:
        """Close the UI, unload the runtime, exit the toolkit - each at most once."""
        surface, self._surface = self._surface, None
        runtime, self._runtime = self._runtime, None
        try:
            if surface is not None:
                surface.close()
        finally:
            try:
                if runtime is not None:
                    runtime.unload()
            finally:
                self._exit_once()

    def _exit_once(self) -> None:
        if self._exited:
            return
        self._exited = True
        self._backend.exit()

    def _loops_line(self, stopped: Sequence[str]) -> str:
        if stopped:
            return f"app: stopping {_plural(len(stopped), 'background loop')}: " + (
                ", ".join(stopped)
            )
        return "app: no background loops were running"

    def __repr__(self) -> str:
        state = (
            "stopped"
            if self._report is not None
            else "running"
            if self._started
            else "new"
        )
        return f"AppSession({self._app_id!r}, {state})"
