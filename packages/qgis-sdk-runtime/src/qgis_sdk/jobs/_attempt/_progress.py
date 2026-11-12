"""The attempt's progress and cancellation services."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._attempt import _Attempt

__all__: list[str] = []


class Progress:
    """The attempt's ``Progress`` service: reported from the worker, delivered on the tick.

    The worker writes and the driving thread reads, so the fields sit behind one
    lock: reporting never blocks and never delivers, and a fraction reported
    between two ticks is delivered once, at the next one. ``observe`` is the
    backend's side of the same signal (``ObservableProgress``): the QGIS task
    manager mirrors it into its task bar, and the callback runs on whichever
    thread reported.
    """

    __slots__ = ("_latest", "_lock", "_observers", "_pending")

    def __init__(self) -> None:
        self._latest: float | None = None
        self._pending = False
        self._observers: list[Callable[[float], None]] = []
        self._lock = threading.Lock()

    def report(self, fraction: float) -> None:
        """Record the latest fraction; the subscriber hears it at the next tick."""
        if not isinstance(fraction, (int, float)) or not 0.0 <= fraction <= 1.0:
            raise ValueError(
                f"progress must be a fraction from 0.0 to 1.0, not {fraction!r}"
            )
        value = float(fraction)
        with self._lock:
            self._latest = value
            self._pending = True
            observers = tuple(self._observers)
        for observer in observers:
            observer(value)

    def observe(self, callback: Callable[[float], None]) -> None:
        """Hear every fraction reported from now on, on the reporting thread."""
        with self._lock:
            self._observers.append(callback)

    @property
    def latest(self) -> float | None:
        with self._lock:
            return self._latest

    def take(self) -> float | None:
        """Return the fraction to deliver now, or ``None`` when nothing is new."""
        with self._lock:
            if not self._pending:
                return None
            self._pending = False
            return self._latest


class Cancellation:
    """The attempt's read-only ``Cancellation`` service, polled from the worker.

    Two sources answer it and either is enough. The attempt's own
    :class:`threading.Event` is set when a handle is cancelled or its owner is
    disposed, and it is the signal a worker polls; the scheduler's token is
    read as well because a host quiescing for a reload cancels the job
    directly. Both are requests, never proof that the body stopped: the
    attempt only settles when the worker reports.
    """

    __slots__ = ("_attempt",)

    def __init__(self, attempt: _Attempt) -> None:
        self._attempt = attempt

    def is_cancelled(self) -> bool:
        return self._attempt.cancelled
