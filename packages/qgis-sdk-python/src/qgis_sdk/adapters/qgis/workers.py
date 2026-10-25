"""``Workers`` over Qt's thread pool: the callable runs there, the job resumes here.

The pool only runs the callable and reports through the job's
:class:`~qgis_sdk.core.scheduling.Handoff`; it never touches the job, a widget
or a layer, and it never delivers anything itself - the step scheduler resumes
the job on the thread that drives it, which is how a worker result reaches
author code on the GUI thread without the worker knowing there is one.

Cancellation is a courtesy here, as decision-21 says it must be: a job
cancelled while its callable is still queued makes the runnable report without
running, and a callable already running is left to finish - it can poll the
job's ``Cancellation`` itself. Nothing is interrupted and no thread is killed.
Closing the owning scope stops new offloads; it does not wait for the pool.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QRunnable, QThreadPool

from qgis_sdk.core import ResourceScope
from qgis_sdk.core.scheduling import Handoff
from qgis_sdk.models import QgisSdkJobCancelledError

__all__ = ["ThreadPoolWorkers"]


class _Runnable(QRunnable):
    """One offloaded callable; reports exactly once, and never raises."""

    def __init__(
        self, fn: Callable[[], Any], handoff: Handoff, cancelled: threading.Event
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._fn = fn
        self._handoff = handoff
        self._cancelled = cancelled

    def run(self) -> None:
        if self._cancelled.is_set():
            # The job will not use a result anyway; report promptly so it can
            # acknowledge its cancellation instead of blocking a replacement.
            owner = self._handoff.owner
            self._handoff.fail(QgisSdkJobCancelledError(owner.id if owner else 0))
            return
        try:
            value = self._fn()
        except BaseException as error:  # noqa: BLE001 - a worker reports, never raises
            self._handoff.fail(error)
            return
        self._handoff.resolve(value)


class ThreadPoolWorkers:
    """Run offloaded callables on a ``QThreadPool`` the host chose."""

    def __init__(
        self, scope: ResourceScope, *, pool: QThreadPool | None = None
    ) -> None:
        scope.ensure_open()
        self._scope = scope
        self._pool = pool if pool is not None else QThreadPool.globalInstance()
        self._offloaded = 0

    @property
    def offloaded(self) -> int:
        """How many callables were handed to the pool."""
        return self._offloaded

    def offload(self, fn: Callable[[], Any]) -> Handoff:
        """Queue ``fn`` on the pool; the job suspends on the returned handoff."""
        self._scope.ensure_open()
        cancelled = threading.Event()
        handoff = Handoff(on_cancel=cancelled.set)
        self._offloaded += 1
        self._pool.start(_Runnable(fn, handoff, cancelled))
        return handoff
