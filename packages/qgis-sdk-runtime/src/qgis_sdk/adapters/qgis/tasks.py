"""``Workers`` over ``QgsTaskManager``: one job body is one visible QGIS task.

Since 0.9.0 the whole job body runs off the driving thread (decision-65), so a
job maps onto exactly one native task: it appears in the QGIS task bar with the
job's title, its progress follows ``ctx.progress``, and the cancel button asks
the job to stop through the same cooperative request a
:class:`~qgis_sdk.jobs.JobHandle` uses. There are no sub-tasks and no second
pool: the only scheduler is the one the host ticks, and the only thread that
delivers is the driving one. A Processing algorithm is already a ``QgsTask``
inside Processing, so it is never wrapped twice here.

Cancellation is a courtesy, as decision-21 says it must be: a job cancelled
while its task is still queued makes the run without calling the body, and a
body already running is left to finish - it can poll ``ctx.cancellation``
itself. Nothing is interrupted and no thread is killed. Closing the owning
scope stops new submissions; it does not wait for the manager.

A task outlives its own ``finished()`` callback, and the adapter never releases
one from inside it. ``QgsTaskManager.addTask`` takes ownership: the manager
keeps working with the task after ``finished()`` returns (it posts
``processSubTasksForCompletion``, emits the completion progress the task bar
draws, then deletes the task). Dropping the last Python reference in
``finished()`` deletes the sip object right there, under the manager's feet,
which crashed inside ``QgsTaskManager::progressChanged`` - intermittently, in
whole-suite runs of the 0.9.0 gate. So ``finished()`` asks Qt to delete the task
with ``deleteLater()`` and hands it to the adapter's retired list; the wrapper
is released only later, from the adapter's own stack (on the next submission or
read), never from a Qt callback, and only after ``destroyed`` says the C++
object is gone.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from qgis.core import QgsApplication, QgsTask, QgsTaskManager

from qgis_sdk.core import ResourceScope
from qgis_sdk.core.scheduling import Handoff
from qgis_sdk.models import QgisSdkJobCancelledError, QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import WorkItem

__all__ = ["QgsTaskWorkers"]


class _JobTask(QgsTask):
    """One job body as a native task; it reports, and never raises."""

    def __init__(
        self,
        fn: Callable[[], Any],
        handoff: Handoff,
        cancelled: threading.Event,
        item: WorkItem | None,
        on_finished: Callable[[], None],
    ) -> None:
        super().__init__(
            item.title if item is not None else "QGIS SDK job",
            QgsTask.Flag.CanCancel,
        )
        self._fn = fn
        self._handoff = handoff
        self._cancelled = cancelled
        self._item = item
        self._on_finished = on_finished
        self._observed = False
        self._retired = False

    # -- Qt's side

    def run(self) -> bool:
        """Run the body on the task manager's worker thread; never touch the GUI."""
        self._mirror_progress()
        if self._cancelled.is_set() or self.isCanceled():
            # Never started, so nothing was done: report the acknowledgement
            # promptly instead of leaving the job as a replacement blocker.
            owner = self._handoff.owner
            self._handoff.fail(QgisSdkJobCancelledError(owner.id if owner else 0))
            return False
        try:
            value = self._fn()
        except BaseException as error:  # noqa: BLE001 - a worker reports, never raises
            self._handoff.fail(error)
            return False
        self._handoff.resolve(value)
        return True

    def finished(self, result: bool) -> None:
        """Qt's completion hook on the driving thread: delivery is the scheduler's.

        The task itself does nothing here beyond letting the adapter forget it -
        not even a message bar, because every callback belongs to the job's
        subscribers and they run on the host's tick.

        Two things must not happen here: deleting the object, because the
        manager keeps working with this task after this method returns (see the
        module docstring), and holding the body's closure any longer than
        needed. So the closure is dropped, progress is no longer mirrored, and
        the task is handed to Qt with ``deleteLater()``; the adapter keeps the
        Python wrapper alive until ``destroyed`` says the object is really gone.
        """
        self._retired = True
        self._fn = None
        self._item = None
        self.deleteLater()
        self._on_finished()

    def cancel(self) -> None:
        """The task bar's cancel button: ask the job to stop, then mark the task."""
        self._request_cancel()
        super().cancel()

    # -- the SDK's side

    def _request_cancel(self) -> None:
        callback = self._item.cancel if self._item is not None else None
        if callback is not None:
            callback()

    def _mirror_progress(self) -> None:
        """Follow the job's progress into the task bar, from the worker thread."""
        if self._observed or self._item is None:
            return
        observe = getattr(self._item.progress, "observe", None)
        if observe is None:
            return
        self._observed = True
        # setProgress takes 0..100 and is safe to call from run(); Qt queues the
        # signal that reaches the task bar on the main thread.
        observe(self._report_progress)

    def _report_progress(self, fraction: float) -> None:
        """Mirror one fraction while the task exists; a retired task ignores it."""
        if self._retired:
            return
        self.setProgress(fraction * 100)


class QgsTaskWorkers:
    """Run each job body as a ``QgsTask`` under the application's task manager.

    ``manager`` defaults to ``QgsApplication.taskManager()``; a host that owns
    one (a test, an embedded application) passes it. ``scope`` is the plugin's:
    closing it stops new submissions, and every task already handed over keeps
    running under the manager's own rules until it reports or is cancelled.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        manager: QgsTaskManager | None = None,
    ) -> None:
        scope.ensure_open()
        resolved = manager if manager is not None else QgsApplication.taskManager()
        if resolved is None:
            raise QgisSdkUnsupportedCapabilityError(
                "QgsTaskManager",
                "the worker backend needs a running QgsApplication; a host "
                "without one has no task manager to run jobs on",
            )
        self._scope = scope
        self._manager = resolved
        # The manager owns the C++ object; this keeps the Python subclass alive
        # while Qt still calls into it, and is emptied as each task finishes.
        self._live: list[_JobTask] = []
        # Finished tasks Qt has been asked to delete but has not deleted yet.
        # Their wrappers must stay alive until ``destroyed`` fires: dropping the
        # last reference deletes the C++ object, and the manager still has work
        # queued for it (see the module docstring).
        self._retired: list[_JobTask] = []
        # Retired wrappers Qt has already destroyed. They are released from
        # this adapter's own stack, never from the ``destroyed`` callback.
        self._gone: list[_JobTask] = []
        self._submitted = 0

    @property
    def submitted(self) -> int:
        """How many job bodies were handed to the task manager."""
        return self._submitted

    @property
    def manager(self) -> QgsTaskManager:
        """The task manager these jobs appear under."""
        return self._manager

    @property
    def tasks(self) -> tuple[QgsTask, ...]:
        """The tasks still running, oldest first - what a host's task bar shows."""
        self._release_gone()
        return tuple(self._live)

    @property
    def retired(self) -> int:
        """How many finished tasks are still waiting for Qt to delete them.

        Zero once Qt has run the ``deleteLater()`` and the adapter has released
        them: this is the count a test asserts to prove finished tasks do not
        pile up, and a host can log it.
        """
        self._release_gone()
        return len(self._retired)

    def offload(
        self, fn: Callable[[], Any], *, item: WorkItem | None = None
    ) -> Handoff:
        """Queue ``fn`` as one task; the job suspends on the returned handoff."""
        self._scope.ensure_open()
        self._release_gone()
        cancelled = threading.Event()
        handoff = Handoff(on_cancel=cancelled.set)
        task = _JobTask(fn, handoff, cancelled, item, lambda: self._forget(task))
        self._live.append(task)
        self._submitted += 1
        self._manager.addTask(task)
        return handoff

    def _forget(self, task: _JobTask) -> None:
        """Stop showing a finished task, keeping it alive until Qt deletes it.

        Called from ``finished()``, so it only moves references: releasing the
        wrapper here is exactly the use-after-free this class documents.
        """
        if task in self._live:
            self._live.remove(task)
        self._release_gone()
        if task in self._retired:
            return
        self._retired.append(task)
        # ``deleteLater`` was requested in ``finished``; ``destroyed`` fires
        # when the C++ object is gone. It only records that fact - the wrapper
        # is released by ``_release_gone``, outside Qt's callback.
        task.destroyed.connect(lambda *_: self._destroyed(task))

    def _destroyed(self, task: _JobTask) -> None:
        """Record that Qt deleted a task; nothing is released in this callback."""
        if task in self._retired:
            self._retired.remove(task)
        if task not in self._gone:
            self._gone.append(task)

    def _release_gone(self) -> None:
        """Drop finished wrappers Qt has already destroyed.

        ``_gone`` never holds anything whose C++ object still exists, so
        clearing it cannot delete a task the manager is using.
        """
        if self._gone:
            self._gone.clear()
