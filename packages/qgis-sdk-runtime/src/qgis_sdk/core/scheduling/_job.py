from __future__ import annotations

from collections.abc import Coroutine, Iterable
from types import MappingProxyType

from qgis_sdk.core.scope import QuiesceOutcome, ResourceScope
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkSchedulingBlockedError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)

from ._states import (
    DEFAULT_QUIESCE_TICKS,
    MAX_STEPS_PER_JOB_PER_TICK,
    CancellationToken,
    Handoff,
    JobMixin1,
    JobState,
    StepOutcome,
    Yield,
    may_run,
)


class _JobMixin2:
    def _settled_by_disposal(self) -> bool:
        """Whether disposal already settled this job while its author code was running."""
        return self._state.settled

    def _settle_on_error(self, error: BaseException) -> StepOutcome:
        """Record how author code ended, keeping a disposal outcome in front of it."""
        if self._settled_by_disposal():
            return StepOutcome.SETTLED
        if isinstance(error, QgisSdkJobCancelledError):
            self._state = JobState.CANCELLED
            return StepOutcome.SETTLED
        self._error = error
        self._state = JobState.FAILED
        return StepOutcome.SETTLED

    def _suspend_on(self, suspended: object) -> StepOutcome:
        """Park the job on what it yielded, or fail it on an unknown awaitable."""
        if isinstance(suspended, Yield):
            self._yielded = True
            self._state = JobState.WAITING
            return StepOutcome.SUSPENDED
        if isinstance(suspended, Handoff):
            suspended._attach(self)
            self._awaiting = suspended
            self._state = JobState.WAITING
            return StepOutcome.SUSPENDED
        self._error = QgisSdkUnsupportedCapabilityError(
            f"awaitable {type(suspended).__name__}"
        )
        self._state = JobState.FAILED
        return StepOutcome.SETTLED

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


class Job(JobMixin1, _JobMixin2):
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
                if outcome is StepOutcome.SETTLED:
                    return
                if not may_run(job):
                    return
        finally:
            # A re-raised interruption unwinds before the settled branch can prune the
            # job, and a settled job left in the active set never advances again while
            # drain() keeps looping.
            if job.settled:
                self._active.pop(job.id, None)
