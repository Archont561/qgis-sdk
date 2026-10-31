"""Drive a job service's tick from the GUI event loop: one ``QTimer`` per plugin.

The scheduler delivers on the tick (decision-13/21/65): progress coalesced to
the latest fraction, and a terminal outcome exactly once, always on the thread
that owns the service. In QGIS that thread is the GUI thread, and a ``QTimer``
is the only supported way to be called on it, so this is the piece that turns
"a job was submitted" into "its subscribers ran".

One pump belongs to one plugin runtime: it starts with the plugin and stops
before the runtime unloads, so no callback runs after the context is gone.
A host that already owns an event loop (a standalone PyQGIS application, the
``qgis-sdk run`` host) uses the same pump, or calls
:meth:`~qgis_sdk.jobs.JobService.tick` from its own timer.
"""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtCore import QTimer

from qgis_sdk.jobs import JobService

__all__ = ["DEFAULT_INTERVAL_MS", "QgsJobPump"]

#: How often the pump ticks by default: short enough that a progress bar looks
#: continuous to a user, long enough that an idle plugin costs nothing.
DEFAULT_INTERVAL_MS = 40


class QgsJobPump:
    """Tick one ``JobService`` on the thread that spins the Qt event loop.

    ``parent`` is handed to the timer so Qt disposes it with its owner; the
    pump itself keeps the Python reference, so a host that forgets to stop it
    still cannot outlive the object it was given.
    """

    #: ``__weakref__`` is not decoration: PyQt6 keeps a weak reference to a
    #: bound slot, and connecting one on a slotted object fails without it.
    __slots__ = ("__weakref__", "_name", "_service", "_timer")

    def __init__(
        self,
        service: JobService,
        *,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        parent: Any | None = None,
        name: str = "job-pump",
    ) -> None:
        if interval_ms <= 0:
            raise ValueError(f"interval_ms must be positive, not {interval_ms!r}")
        self._name = name
        self._service = service
        self._timer = QTimer(parent)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    @property
    def name(self) -> str:
        """What this loop is called in a host's shutdown report (decision-69 §4)."""
        return self._name

    @property
    def service(self) -> JobService:
        """The job service this pump advances."""
        return self._service

    @property
    def interval_ms(self) -> int:
        """How often the pump ticks, in milliseconds."""
        return self._timer.interval()

    @property
    def running(self) -> bool:
        """Whether the timer is armed."""
        return self._timer.isActive()

    def start(self) -> None:
        """Arm the timer; calling it twice is harmless."""
        self._timer.start()

    def stop(self) -> None:
        """Disarm the timer; safe to call when it never started."""
        self._timer.stop()

    def tick(self) -> int:
        """Advance the service once, now: what the timer does, for a test."""
        return self._service.tick()

    def _tick(self) -> None:
        self._service.tick()

    def __repr__(self) -> str:
        state = "running" if self.running else "stopped"
        return f"QgsJobPump({self._name!r}, {state}, {self.interval_ms}ms)"
