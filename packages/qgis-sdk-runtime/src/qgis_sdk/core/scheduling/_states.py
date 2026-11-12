"""Cooperative step scheduling for coroutine-based plugin work.

This module is QGIS-free and thread-free by design. The scheduler starts no worker
and resumes author code in no worker callback: it advances each active job by a
bounded number of steps per :meth:`StepScheduler.tick`, so the thread driving the
tick — the QGIS GUI thread in a Desktop host — stays responsive. Worker results
travel back through a :class:`Handoff` mailbox and reach the job on the driving
thread at its next step.

Cancellation and disposal follow ADR-21: a request is honoured at the job's next
suspension point, work that cannot reach a safe point is reported as a blocker, and
a refused replacement is never forced. Two further rules keep the observable outcome
honest. Control flow that is not an :class:`Exception` -- an interpreter exit or a
debug interrupt raised through author code -- is recorded on the job and then
re-raised to whoever is driving the tick, never absorbed as a quiet job failure. And
once disposal has settled a job, that settlement is final: author code that is
already on the stack cannot complete, re-suspend or re-attach a handoff afterwards.
The scheduler is the measured mechanism; selecting public async syntax stays a
separate decision.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from enum import StrEnum
from queue import Empty, SimpleQueue
from typing import TYPE_CHECKING, Any

from qgis_sdk.core.scope import QuiesceOutcome
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
)

if TYPE_CHECKING:
    from qgis_sdk.core.scheduling._job import Job

MAX_STEPS_PER_JOB_PER_TICK = 8
"""Steps one job may take before the tick moves on to the next job."""
DEFAULT_QUIESCE_TICKS = 32
"""Bounded window a host waits for work to acknowledge before refusing reload."""


class JobState(StrEnum):
    """Observable scheduling state of one submitted job."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def settled(self) -> bool:
        """Whether the job can no longer advance."""
        return self in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)


class StepOutcome(StrEnum):
    """Internal classification of one scheduler step."""

    SUSPENDED = "suspended"
    SETTLED = "settled"


class _Discarded:
    """Marks a handoff whose owning scope is gone, so reports count as dropped."""


_DISCARDED = _Discarded()


@dataclass(frozen=True, slots=True)
class _Report:
    """One worker outcome handed to the scheduler, never applied by the worker."""

    error: BaseException | None
    value: object


class Yield:
    """Return control to the host event loop until the next scheduler tick."""

    __slots__ = ()

    def __await__(self) -> Generator[Yield, None, None]:
        yield self


class Handoff:
    """One result a worker reports back to the thread driving the scheduler.

    :meth:`resolve` and :meth:`fail` are safe to call from any thread: they only
    enqueue a value. The awaiting job resumes at its next step, never inside the
    call, which is what keeps a worker from running GUI-affine code.

    ``on_cancel`` lets a worker that *can* stop early - a network request, a
    cancellable native task - hear that its job was cancelled while suspended on
    this handoff. It runs at most once, on the thread that called
    :meth:`Job.cancel`, and the job still resumes only when the worker reports:
    the hook is a request, not proof that the worker stopped.
    """

    __slots__ = ("_box", "_dropped", "_on_cancel", "_owner")

    def __init__(self, *, on_cancel: Callable[[], None] | None = None) -> None:
        self._box: SimpleQueue[_Report] = SimpleQueue()
        self._owner: Job | _Discarded | None = None
        self._dropped = 0
        self._on_cancel = on_cancel

    @property
    def owner(self) -> Job | None:
        """Return the job currently suspended on this handoff, if any."""
        from ._job import Job

        owner = self._owner
        return owner if isinstance(owner, Job) else None

    @property
    def reported(self) -> bool:
        """Whether a worker has already reported an outcome."""
        return not self._box.empty()

    @property
    def dropped_reports(self) -> int:
        """Return how many reports arrived too late to reach an owner."""
        return self._dropped

    def resolve(self, value: object = None) -> None:
        """Report success; the awaiting job keeps waiting until its next step."""
        self._report(_Report(None, value))

    def fail(self, error: BaseException) -> None:
        """Report failure; the awaiting job keeps waiting until its next step."""
        self._report(_Report(error, None))

    def _report(self, report: _Report) -> None:
        """Hand a worker outcome to the owning job, or count it as too late.

        A report for a detached handoff is dropped rather than queued: nothing is
        ever delivered to an owner that disposal already settled.
        """
        if isinstance(self._owner, _Discarded):
            self._dropped += 1
            return
        self._box.put(report)

    def __await__(self) -> Generator[Handoff, object, object]:
        """Yield this handoff itself, so the scheduler sees what the job waits on."""
        return (yield self)

    def _request_cancel(self) -> None:
        """Tell the worker once that the suspended job no longer wants the result."""
        hook = self._on_cancel
        self._on_cancel = None
        if hook is not None:
            hook()

    def _attach(self, job: Job) -> None:
        """Claim this handoff for the job suspending on it.

        Called by :class:`Job._suspend_on` on the way into ``WAITING``; the owner is
        who a worker report is routed to, so a handoff has exactly one claimant.
        """
        self._owner = job

    def _release(self) -> None:
        """Forget the job that consumed this handoff, so it is no longer its owner."""
        self._owner = None

    def _detach(self) -> None:
        """Stop delivering to a disposed owner and count anything left undelivered."""
        self._owner = _DISCARDED
        while not self._box.empty():
            self._box.get_nowait()
            self._dropped += 1

    def _take(self) -> _Report | None:
        """Claim the reported outcome once, without blocking the calling thread.

        Called by :class:`Job._step` at the job's next step, never from the worker
        thread; an empty box returns ``None`` so one report cannot settle two steps.
        """
        try:
            return self._box.get_nowait()
        except Empty:
            return None


def may_run(job: Job) -> bool:
    """Whether author code may run again inside the current tick.

    A job that has not yielded and is not waiting on a handoff is runnable; a
    handoff that has been reported means the awaiting code may resume.
    """
    if job._yielded:
        return False
    handoff = job._awaiting
    return handoff is None or handoff.reported


class CancellationToken:
    """The scheduler side of the ``services.Cancellation`` contract."""

    __slots__ = ("_job", "_requested")

    def __init__(self, job: Job) -> None:
        self._job = job
        self._requested = False

    @property
    def job(self) -> Job:
        """Return the job this signal belongs to."""
        return self._job

    def is_cancelled(self) -> bool:
        """Return whether cancellation was requested for this job."""
        return self._requested

    def _request(self, settled: bool) -> bool:
        """Record a request; return whether the job was still active."""
        already_requested = self._requested
        self._requested = True
        return not already_requested and not settled


class JobMixin1:
    @property
    def id(self) -> int:
        """Return the scheduler-assigned job identifier."""
        return self._id

    @property
    def state(self) -> JobState:
        """Return the current scheduling state."""
        return self._state

    @property
    def result(self) -> object:
        """Return the value a completed job returned."""
        return self._result

    @property
    def error(self) -> BaseException | None:
        """Return the exception that made the job fail, if any."""
        return self._error

    @property
    def cancellation(self) -> CancellationToken:
        """Return the read-only signal long-running steps poll cooperatively."""
        return self._cancellation

    @property
    def awaiting(self) -> Handoff | None:
        """Return the handoff this job is suspended on, if any."""
        return self._awaiting

    @property
    def steps(self) -> int:
        """Return how many times author code has run for this job."""
        return self._steps

    @property
    def settled(self) -> bool:
        """Return whether the job can no longer advance."""
        return self._state.settled

    def cancel(self) -> bool:
        """Request cancellation; return whether the job was still active.

        A job suspended on a handoff cannot be resumed until its worker reports,
        so the handoff is told as well; a worker with a cancel hook can then
        report early instead of leaving the job as a replacement blocker.
        """
        active = self._cancellation._request(self._state.settled)
        if active and self._awaiting is not None:
            self._awaiting._request_cancel()
        return active

    def _step(self, *, cancel_requested: bool) -> StepOutcome:
        """Advance author code once, honouring a pending cancellation first."""
        self._yielded = False
        if self._state is JobState.QUEUED:
            self._state = JobState.RUNNING
            if cancel_requested:
                self._coro.close()
                self._state = JobState.CANCELLED
                return StepOutcome.SETTLED
            return self._drive(None, throw=False)
        handoff = self._awaiting
        if handoff is not None:
            return self._resume(handoff, cancel_requested)
        if cancel_requested and not self._cancel_delivered:
            return self._deliver_cancellation()
        return self._drive(None, throw=False)

    def _resume(self, handoff: Any, cancel_requested: bool) -> StepOutcome:
        """Deliver the report one suspension left, or wait for it."""
        report = handoff._take()
        if report is None:
            return StepOutcome.SUSPENDED
        handoff._release()
        self._awaiting = None
        if cancel_requested and not self._cancel_delivered:
            return self._deliver_cancellation()
        if report.error is not None:
            return self._drive(report.error, throw=True)
        return self._drive(report.value, throw=False)

    def _deliver_cancellation(self) -> StepOutcome:
        """Throw the cancellation in so author cleanup can run."""
        self._cancel_delivered = True
        return self._drive(QgisSdkJobCancelledError(self._id), throw=True)

    def _drive(self, payload: object, *, throw: bool) -> StepOutcome:
        """Run one suspension of the coroutine and classify what it yielded."""
        self._started = True
        self._state = JobState.RUNNING
        self._steps += 1
        drive = self._coro.throw if throw else self._coro.send
        try:
            suspended = drive(payload)
        except StopIteration as stop:
            if self._settled_by_disposal():
                return StepOutcome.SETTLED
            self._result = stop.value
            self._state = JobState.COMPLETED
            return StepOutcome.SETTLED
        except Exception as error:  # noqa: BLE001 - recorded, then re-raised
            return self._settle_on_error(error)
        except BaseException as error:
            # Anything that is not an Exception is the host's own control flow: an
            # interpreter exit or a debug interrupt. Record it so the job does not
            # lie about its outcome, then hand it back instead of swallowing it.
            self._settle_on_error(error)
            raise
        if self._settled_by_disposal():
            return StepOutcome.SETTLED
        return self._suspend_on(suspended)


__all__ = [
    "QuiesceOutcome",
]
