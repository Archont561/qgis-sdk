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

from collections.abc import Callable, Coroutine, Generator, Iterable
from dataclasses import dataclass
from enum import StrEnum
from queue import Empty, SimpleQueue
from types import MappingProxyType

from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkSchedulingBlockedError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)

from .scope import QuiesceOutcome, ResourceScope

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


class _StepOutcome(StrEnum):
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


class Job:
    """Handle for one submitted job: state, outcome and cancellation request."""

    __slots__ = (
        "_awaiting",
        "_cancel_delivered",
        "_cancellation",
        "_coro",
        "_error",
        "_id",
        "_result",
        "_started",
        "_state",
        "_steps",
        "_yielded",
    )

    def __init__(self, identifier: int, coro: Coroutine[object, None, object]) -> None:
        self._id = identifier
        self._coro = coro
        self._state = JobState.QUEUED
        self._result: object = None
        self._error: BaseException | None = None
        self._started = False
        self._yielded = False
        self._steps = 0
        self._awaiting: Handoff | None = None
        self._cancel_delivered = False
        self._cancellation = CancellationToken(self)

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

    @property
    def _ready(self) -> bool:
        """Whether author code may run again inside the current tick."""
        if self._yielded:
            return False
        handoff = self._awaiting
        return handoff is None or handoff.reported

    def _step(self, *, cancel_requested: bool) -> _StepOutcome:
        """Advance author code once, honouring a pending cancellation first."""
        self._yielded = False
        if self._state is JobState.QUEUED:
            self._state = JobState.RUNNING
            if cancel_requested:
                self._coro.close()
                self._state = JobState.CANCELLED
                return _StepOutcome.SETTLED
            return self._drive(None, throw=False)
        handoff = self._awaiting
        if handoff is not None:
            report = handoff._take()
            if report is None:
                return _StepOutcome.SUSPENDED
            handoff._release()
            self._awaiting = None
            if cancel_requested and not self._cancel_delivered:
                return self._deliver_cancellation()
            if report.error is not None:
                return self._drive(report.error, throw=True)
            return self._drive(report.value, throw=False)
        if cancel_requested and not self._cancel_delivered:
            return self._deliver_cancellation()
        return self._drive(None, throw=False)

    def _deliver_cancellation(self) -> _StepOutcome:
        """Throw the cancellation in so author cleanup can run."""
        self._cancel_delivered = True
        return self._drive(QgisSdkJobCancelledError(self._id), throw=True)

    def _drive(self, payload: object, *, throw: bool) -> _StepOutcome:
        """Run one suspension of the coroutine and classify what it yielded."""
        self._started = True
        self._state = JobState.RUNNING
        self._steps += 1
        drive = self._coro.throw if throw else self._coro.send
        try:
            suspended = drive(payload)
        except StopIteration as stop:
            if self._settled_by_disposal():
                return _StepOutcome.SETTLED
            self._result = stop.value
            self._state = JobState.COMPLETED
            return _StepOutcome.SETTLED
        except Exception as error:  # noqa: BLE001 - an author failure is a job outcome
            return self._settle_on_error(error)
        except BaseException as error:
            # Anything that is not an Exception is the host's own control flow: an
            # interpreter exit or a debug interrupt. Record it so the job does not
            # lie about its outcome, then hand it back instead of swallowing it.
            self._settle_on_error(error)
            raise
        if self._settled_by_disposal():
            return _StepOutcome.SETTLED
        return self._suspend_on(suspended)

    def _settled_by_disposal(self) -> bool:
        """Whether disposal already settled this job while its author code was running."""
        return self._state.settled

    def _settle_on_error(self, error: BaseException) -> _StepOutcome:
        """Record how author code ended, keeping a disposal outcome in front of it."""
        if self._settled_by_disposal():
            return _StepOutcome.SETTLED
        if isinstance(error, QgisSdkJobCancelledError):
            self._state = JobState.CANCELLED
            return _StepOutcome.SETTLED
        self._error = error
        self._state = JobState.FAILED
        return _StepOutcome.SETTLED

    def _suspend_on(self, suspended: object) -> _StepOutcome:
        """Park the job on what it yielded, or fail it on an unknown awaitable."""
        if isinstance(suspended, Yield):
            self._yielded = True
            self._state = JobState.WAITING
            return _StepOutcome.SUSPENDED
        if isinstance(suspended, Handoff):
            suspended._attach(self)
            self._awaiting = suspended
            self._state = JobState.WAITING
            return _StepOutcome.SUSPENDED
        self._error = QgisSdkUnsupportedCapabilityError(
            f"awaitable {type(suspended).__name__}"
        )
        self._state = JobState.FAILED
        return _StepOutcome.SETTLED

    def _abandon(self) -> None:
        """Detach the job from a disposed scope without resuming author code."""
        handoff = self._awaiting
        if handoff is not None:
            handoff._detach()
            self._awaiting = None
        # The reason is recorded even when author code never ran, so a job the host
        # still holds a handle on does not report a failure with no explanation.
        self._error = QgisSdkScopeClosedError()
        if not self._started:
            # Closing is safe only while the coroutine is unstarted: a started one
            # would run a pending ``finally`` against native objects that are gone,
            # which is exactly what disposal exists to prevent. Its frame stays
            # suspended until the host drops the handle, rather than being resumed to
            # unwind.
            self._coro.close()
        if self._cancellation.is_cancelled():
            self._state = JobState.CANCELLED
        else:
            self._state = JobState.FAILED


class StepScheduler:
    """Advance coroutine jobs one bounded step per tick on the host's own thread.

    The scheduler owns no thread and no timer: a runtime adapter calls
    :meth:`tick` from the event loop it already has, which is what makes GUI-thread
    handoff observable instead of implied by the presence of ``async def``.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        max_steps_per_job: int = MAX_STEPS_PER_JOB_PER_TICK,
    ) -> None:
        if max_steps_per_job < 1:
            raise ValueError("max_steps_per_job must be at least 1")
        self._scope = scope
        self._max_steps_per_job = max_steps_per_job
        self._active: dict[int, Job] = {}
        self._next_id = 0
        self._quiescing = False
        self._discarded: list[Handoff] = []
        scope.on_close(self.dispose)

    @property
    def jobs(self) -> MappingProxyType[int, Job]:
        """Return the active jobs, keyed by ID, in submission order."""
        return MappingProxyType(dict(self._active))

    @property
    def closed(self) -> bool:
        """Whether the owning scope has been disposed."""
        return self._scope.closed

    @property
    def quiescing(self) -> bool:
        """Whether new submissions are refused pending replacement."""
        return self._quiescing

    @property
    def dropped_reports(self) -> int:
        """Return how many worker reports arrived after their owner was disposed."""
        return sum(handoff.dropped_reports for handoff in self._discarded)

    def submit(self, coro: Coroutine[object, None, object]) -> Job:
        """Register a coroutine as a job without running any author code yet."""
        try:
            self._scope.ensure_open()
        except QgisSdkScopeClosedError:
            coro.close()
            raise
        if self._quiescing:
            coro.close()
            raise QgisSdkSchedulingBlockedError(
                ["the scheduler is quiescing for replacement"]
            )
        self._next_id += 1
        job = Job(self._next_id, coro)
        self._active[job.id] = job
        return job

    def tick(self) -> int:
        """Advance every active job within its step budget; return author steps run."""
        steps = 0
        for job in tuple(self._active.values()):
            before = job.steps
            self._advance(job)
            steps += job.steps - before
        return steps

    def drain(self, *, max_ticks: int | None = None) -> int:
        """Tick until no job remains active or ``max_ticks`` is reached."""
        ticks = 0
        while self._active and (max_ticks is None or ticks < max_ticks):
            self.tick()
            ticks += 1
        return ticks

    def quiesce(self, *, max_ticks: int = DEFAULT_QUIESCE_TICKS) -> QuiesceOutcome:
        """Request cancellation of all work and look for a safe replacement point.

        Refusal is a result rather than an exception: the host keeps the current
        generation running and names the blocker, instead of deleting native
        resources under a worker that never acknowledged the stop request.
        """
        self._quiescing = True
        for job in tuple(self._active.values()):
            job.cancel()
        for _ in range(max_ticks):
            if not self._active:
                break
            self.tick()
        blockers = tuple(self._blockers())
        if blockers:
            return QuiesceOutcome(refused=True, blockers=blockers)
        self._quiescing = False
        return QuiesceOutcome(refused=False, blockers=())

    def resume(self) -> None:
        """Accept new work again after a refused or abandoned replacement."""
        self._quiescing = False

    def close(self) -> None:
        """Dispose the owning scope, which detaches every active job."""
        self._scope.close()

    def dispose(self) -> None:
        """Abandon active jobs after the owner disposed the scope.

        Author coroutines are not resumed, so a pending ``finally`` cannot touch
        native objects that are already gone, later worker reports are counted as
        dropped instead of delivered, and a job that is already settled by this call
        keeps that outcome whatever its author code does next.
        """
        for job in tuple(self._active.values()):
            self.abandon(job)
        self._active.clear()

    def abandon(self, job: Job) -> bool:
        """Drop one job without resuming author code; return whether it was active.

        Dispatching with the same rule a disposed scope uses, for a host that is
        done with one owner while the rest of the plugin keeps working - a QGIS
        Server request whose response has been sent (decision-52). A worker
        report that arrives afterwards is counted as dropped rather than
        delivered, and a job that already started keeps its state without
        running a pending ``finally`` against resources that are gone.

        A job that already settled is left alone - there is nothing to drop and
        its outcome is the one its owner can still read - so this answers
        ``False`` instead of overwriting it.
        """
        if job.id not in self._active:
            return False
        handoff = job.awaiting
        if handoff is not None:
            self._discarded.append(handoff)
        job._abandon()
        return self._active.pop(job.id, None) is not None

    def _blockers(self) -> Iterable[str]:
        """Name every job that cannot reach a safe point, in submission order."""
        for job in self._active.values():
            if job.awaiting is not None:
                yield f"job {job.id} is waiting on an unresolved worker handoff"
            else:
                yield f"job {job.id} is still {job.state.value} after cancellation"

    def _advance(self, job: Job) -> None:
        """Spend one job's step budget, stopping at the first unsafe point.

        The membership check is what keeps a job that this very loop abandoned -
        disposal can land mid-step - from being driven a second time.
        """
        try:
            for _ in range(self._max_steps_per_job):
                if job.settled or job.id not in self._active:
                    return
                outcome = job._step(cancel_requested=job.cancellation.is_cancelled())
                if outcome is _StepOutcome.SETTLED:
                    return
                if not job._ready:
                    return
        finally:
            # A re-raised interruption unwinds before the settled branch can prune the
            # job, and a settled job left in the active set never advances again while
            # drain() keeps looping.
            if job.settled:
                self._active.pop(job.id, None)
