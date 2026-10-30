"""The attempt: one run of a job on the step scheduler, progress and cancellation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
)

from qgis_sdk.core import ResourceScope, WorkerContext
from qgis_sdk.core.scheduling import Job
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    type_name,
)
from qgis_sdk.jobs._authoring import (
    _EVENTS,
    _STATUS_OF_STATE,
    JobDescription,
    JobEvent,
    JobStatus,
    _accepts,
)
from qgis_sdk.jobs._subscriptions import JobFault, JobSubscription
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkJobNotSettledError,
    QgisSdkScopeClosedError,
)

if TYPE_CHECKING:
    from qgis_sdk.jobs._service import JobService, _Runtime


# -- the attempt --------------------------------------------------------------------


class _Progress:
    """The attempt's ``Progress`` service: reported from the worker, delivered on the tick.

    The worker writes and the driving thread reads, so the two fields sit
    behind one lock: reporting never blocks and never delivers, and a fraction
    reported between two ticks is delivered once, at the next one.
    """

    __slots__ = ("_latest", "_lock", "_pending")

    def __init__(self) -> None:
        self._latest: float | None = None
        self._pending = False
        self._lock = threading.Lock()

    def report(self, fraction: float) -> None:
        """Record the latest fraction; the subscriber hears it at the next tick."""
        if not isinstance(fraction, (int, float)) or not 0.0 <= fraction <= 1.0:
            raise ValueError(
                f"progress must be a fraction from 0.0 to 1.0, not {fraction!r}"
            )
        with self._lock:
            self._latest = float(fraction)
            self._pending = True

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


class _Cancellation:
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


class _Attempt:
    """Everything the service tracks about one submitted job."""

    def __init__(
        self,
        *,
        runtime: _Runtime,
        owner: JobService,
        description: JobDescription,
        logical_id: str,
    ) -> None:
        self.runtime = runtime
        self.owner = owner
        self.description = description
        self.id = logical_id
        self.attempt = 1
        self.scope = runtime.scope.child()
        self.progress = _Progress()
        self._cancelled = threading.Event()
        self._job: Job | None = None
        self._subscriptions: dict[JobEvent, dict[JobSubscription, None]] = {
            event: {} for event in _EVENTS
        }
        self._owner_closed = False
        self.delivered = False
        self.settled = threading.Event()

    @property
    def owner_closed(self) -> bool:
        """Whether the owner is gone - told so, or found so after the attempt finished.

        A finished attempt leaves the service's books, so it is not told when
        its owner closes later; asking the scope keeps a late subscription on
        such a handle from replaying into a disposed view.
        """
        return self._owner_closed or self.owner._scope.closed

    @property
    def job(self) -> Job:
        job = self._job
        assert job is not None, "an attempt is submitted before it is handed out"
        return job

    @property
    def cancelled(self) -> bool:
        """Whether a cancellation was requested: by the owner or a quiesce.

        Read from a worker through ``ctx.cancellation.is_cancelled()``, so the
        first half is a :class:`threading.Event`; the scheduler's request
        covers a host quiescing for a replacement.
        """
        job = self._job
        return self._cancelled.is_set() or (
            job is not None and job.cancellation.is_cancelled()
        )

    @property
    def status(self) -> JobStatus:
        return _STATUS_OF_STATE[self.job.state]

    @property
    def error(self) -> BaseException | None:
        return self.job.error if self.status is JobStatus.FAILED else None

    def outcome(self) -> object:
        """Return the result, or raise what stands in its place."""
        status = self.status
        if status is JobStatus.SUCCEEDED:
            return self.job.result
        if status is JobStatus.CANCELLED:
            raise QgisSdkJobCancelledError(self.job.id)
        if status is JobStatus.FAILED:
            error = self.job.error
            assert error is not None, "a failed job records its error"
            raise error
        raise QgisSdkJobNotSettledError(self.id, status.value)

    # -- subscriptions

    def subscribe(
        self, event: JobEvent, callback: Callable, owner: ResourceScope | None
    ) -> JobSubscription:
        if self.owner_closed:
            raise QgisSdkScopeClosedError()
        if owner is not None:
            owner.ensure_open()
        # The job's own owner detaches everything on disposal; only a
        # different owner needs a hook of its own, held per scope so a
        # finished job leaves nothing behind on it.
        hooked = owner if owner is not None and owner is not self.owner._scope else None
        subscription = JobSubscription(self, event, callback, hooked)
        if self._replay(subscription):
            return subscription
        self._subscriptions[event][subscription] = None
        if hooked is not None:
            self.runtime.add_owner_hook(hooked, subscription)
        return subscription

    def _replay(self, subscription: JobSubscription) -> bool:
        """Deliver the current state once; return whether that completed it."""
        event = subscription.event
        status = self.status
        if event == "progress":
            latest = self.progress.latest
            if latest is not None:
                self._invoke(subscription, latest)
            if status.settled:
                subscription._active = False
                return True
            return False
        if not status.settled:
            return False
        if event == _TERMINAL_EVENT[status]:
            self._invoke(subscription, *self._terminal_payload())
        subscription._active = False
        return True

    def detach(self) -> None:
        """Dispose every subscription; nothing is delivered after this."""
        for registry in self._subscriptions.values():
            for subscription in tuple(registry):
                subscription.dispose()

    def _invoke(self, subscription: JobSubscription, *payload: object) -> None:
        try:
            subscription._callback(*payload)
        except Exception as error:  # noqa: BLE001 - a subscriber fault is reported
            subscription.dispose()
            self.runtime.fault(JobFault(self.id, subscription.event, error))

    def _emit(self, event: JobEvent, *payload: object) -> None:
        for subscription in tuple(self._subscriptions[event]):
            if subscription.active:
                self._invoke(subscription, *payload)

    def _terminal_payload(self) -> tuple[object, ...]:
        status = self.status
        if status is JobStatus.SUCCEEDED:
            return (self.job.result,)
        if status is JobStatus.FAILED:
            return (self.job.error,)
        return ()

    # -- delivery, on the tick

    def deliver(self) -> None:
        """Hand the subscribers what changed since the last tick."""
        fraction = self.progress.take()
        if fraction is not None and not self.owner_closed:
            self._emit("progress", fraction)
        status = self.status
        if not status.settled or self.delivered:
            return
        self.delivered = True
        if not self.owner_closed:
            self._emit(_TERMINAL_EVENT[status], *self._terminal_payload())
        self.finish()

    def finish(self) -> None:
        """Complete the attempt: no more callbacks, waiters wake, the scope closes."""
        self.detach()
        self.settled.set()
        self.runtime.attempts.pop(self.id, None)
        if not self.scope.closed:
            self.scope.close()

    # -- ownership

    def owner_disposed(self) -> None:
        """The owning view is gone: detach now, ask the job to stop, keep the attempt."""
        self._owner_closed = True
        self.detach()
        self.request_cancel()

    def request_cancel(self) -> None:
        """Ask the worker to stop; the attempt keeps the outcome until it reports."""
        self._cancelled.set()
        self.job.cancel()

    def abandoned(self) -> None:
        """The plugin is gone: the scheduler abandons the job; nobody is called."""
        self._owner_closed = True
        self.detach()
        self.settled.set()


_TICK_IN_PROGRESS = "a tick is already in progress on this thread"
_NOT_THE_DRIVING_THREAD = (
    "the tick and quiesce belong to the thread that built the service; a job "
    "body runs on a worker and has no tick of its own"
)

_TERMINAL_EVENT: dict[JobStatus, JobEvent] = {
    JobStatus.SUCCEEDED: "success",
    JobStatus.FAILED: "failure",
    JobStatus.CANCELLED: "cancelled",
}


async def _run_attempt(
    attempt: _Attempt, function: Callable[..., Any], arguments: dict[str, Any]
) -> object:
    """Hand the whole body to a worker, wait for it here, check what came back.

    The coroutine itself only ever runs on the driving thread: it submits a
    callable and suspends on the worker's handoff, so the body is never
    executed by whoever called :meth:`JobService.tick`. The context built for
    that callable carries progress and cancellation and refuses everything
    else (decision-65); the result is validated here, on the driving thread,
    before any subscriber sees it.
    """
    attempt.scope.ensure_open()
    workers = attempt.runtime.workers
    assert workers is not None, "submission is refused without a worker backend"
    context = WorkerContext(
        progress=attempt.progress,
        cancellation=_Cancellation(attempt),
    )
    handoff = workers.offload(lambda: function(context, **arguments))
    outcome = await handoff
    description = attempt.description
    if not _accepts(outcome, description.result_type):
        raise QgisSdkDeclarationError(
            f"{description.id}: returned {type_name(type(outcome))}, not the "
            f"declared {type_name(description.result_type)}"
        )
    return outcome
