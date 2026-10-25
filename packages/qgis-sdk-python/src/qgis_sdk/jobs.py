"""Scoped local jobs: one decorated class per job, bound to an owner, typed end to end.

decision-13 fixed the authoring and submission shape - ``@job`` on a plain class
with a typed ``run(inputs) -> Result``, submitted as
``ctx.jobs.bind(JobClass).delay(inputs)`` - and decision-21 fixed what owns the
work: a view by default, a plugin only explicitly, with disposal detaching the
view's callbacks at once and *requesting* cancellation rather than pretending
to have it. This module is both, over the TASK-13 step scheduler, and it is
QGIS-free: a host drives :meth:`JobService.tick` from the event loop it already
has, and that is the only thread author callbacks ever run on.

Three rules carry the rest of the design and are worth stating once:

* **A request is not a state.** :meth:`JobHandle.cancel` sets
  :attr:`JobHandle.cancel_requested`; :attr:`JobHandle.status` becomes
  ``cancelled`` only when the job acknowledges it at a suspension point (or
  before it ever started). Work that completes anyway reports success.
* **Callbacks are delivered on the tick, never from a worker.** Progress
  reported from a worker thread is coalesced to the latest fraction and
  delivered on the next tick; a terminal outcome is delivered exactly once.
  Subscribing after the fact replays the current state synchronously, once,
  and a terminal replay completes the subscription (decision-13).
* **Disposal beats delivery.** Closing the owner scope disposes every
  subscription it owns before anything else happens; a job the view no longer
  owns is asked to stop, but its attempt is not torn down under a worker that
  has not reported. Plugin unload is the one place everything is abandoned,
  and that is the scheduler's existing rule, not a new one.

No retries exist here, by decision. Resubmission is ``delay`` again, with a new
logical id; ``attempt`` is always ``1`` and is carried so a later, explicit
retry policy has somewhere to count.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, TypeVar

from qgis_sdk.core import JobContext, ResourceScope
from qgis_sdk.core.scheduling import Job, JobState, QuiesceOutcome, StepScheduler
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    canonical_json,
    class_decorator,
    describe_run_method,
    register_describer,
    type_name,
)
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkJobNotSettledError,
    QgisSdkJobRejectedError,
    QgisSdkJobWaitRefusedError,
    QgisSdkScopeClosedError,
)
from qgis_sdk.services import Network, Workers

__all__ = [
    "BoundJob",
    "JobDescription",
    "JobEvent",
    "JobFault",
    "JobHandle",
    "JobService",
    "JobStatus",
    "JobSubscription",
    "describe_job",
    "job",
]

T = TypeVar("T")

_JOB_ATTRIBUTE = "__qgis_sdk_job__"

JobEvent = Literal["progress", "success", "failure", "cancelled"]
"""The four things a handle can be subscribed to."""

_EVENTS: tuple[JobEvent, ...] = ("progress", "success", "failure", "cancelled")


def _main_thread() -> bool:
    """The default notion of "the GUI thread": the interpreter's main thread."""
    return threading.current_thread() is threading.main_thread()


# -- authoring --------------------------------------------------------------------


class JobStatus(StrEnum):
    """The observable state of one submitted job (decision-13 names)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def settled(self) -> bool:
        """Whether the job can no longer change state."""
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


_STATUS_OF_STATE = {
    JobState.QUEUED: JobStatus.QUEUED,
    JobState.RUNNING: JobStatus.RUNNING,
    JobState.WAITING: JobStatus.RUNNING,
    JobState.COMPLETED: JobStatus.SUCCEEDED,
    JobState.FAILED: JobStatus.FAILED,
    JobState.CANCELLED: JobStatus.CANCELLED,
}


def job(
    cls: type[T] | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach job metadata without wrapping or constructing the class.

    ``@job`` alone derives the id and title from the class name, the way
    ``@plugin`` does; ``id=`` and ``title=`` override either one.
    """
    return class_decorator(_JOB_ATTRIBUTE, "@job", cls, id=id, title=title)


@dataclass(frozen=True)
class JobDescription:
    """Inspectable job structure: its typed inputs and result, and how it runs.

    ``asynchronous`` says whether ``run`` is a coroutine function. A plain
    ``run`` executes in one scheduler step on the driving thread, so it is for
    short work or work that hands itself off through ``ctx.workers``; an
    ``async def run`` suspends on the scheduler at every ``await``.
    """

    id: str
    title: str
    inputs_type: Any
    result_type: Any
    inputs_schema: dict[str, Any]
    result_schema: dict[str, Any]
    asynchronous: bool
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation without live Python types."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "asynchronous": self.asynchronous,
            "inputs": {
                "type": type_name(self.inputs_type),
                "schema": self.inputs_schema,
            },
            "result": {
                "type": type_name(self.result_type),
                "schema": self.result_schema,
            },
        }

    def to_json(self) -> str:
        """The canonical JSON form shared by every description."""
        return canonical_json(self.to_dict())


def describe_job(cls: type) -> JobDescription:
    """Inspect one decorated class without constructing it or calling ``run``."""
    signature = describe_run_method(cls, _JOB_ATTRIBUTE, "job")
    return JobDescription(
        id=signature.metadata.id,
        title=signature.metadata.title,
        inputs_type=signature.inputs_type,
        result_type=signature.result_type,
        inputs_schema=signature.inputs_schema,
        result_schema=signature.result_schema,
        asynchronous=signature.asynchronous,
    )


register_describer(_JOB_ATTRIBUTE, describe_job)


# -- subscriptions ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobFault:
    """A subscriber that raised; it was detached and the job carried on."""

    job_id: str
    event: JobEvent
    error: BaseException


class JobSubscription:
    """One disposable callback registration on a handle."""

    __slots__ = ("_active", "_attempt", "_callback", "_event", "_owner")

    def __init__(
        self,
        attempt: _Attempt,
        event: JobEvent,
        callback: Callable,
        owner: ResourceScope | None = None,
    ) -> None:
        self._attempt = attempt
        self._event = event
        self._callback = callback
        self._owner = owner
        self._active = True

    @property
    def event(self) -> JobEvent:
        """Which of the four events this subscription listens to."""
        return self._event

    @property
    def active(self) -> bool:
        """Whether the callback can still be invoked."""
        return self._active

    def dispose(self) -> bool:
        """Stop delivery; return whether this call was the one that stopped it."""
        if not self._active:
            return False
        self._active = False
        self._attempt._subscriptions[self._event].pop(self, None)
        if self._owner is not None:
            self._attempt.runtime.release_owner_hook(self._owner, self)
        return True


# -- the attempt --------------------------------------------------------------------


class _Progress:
    """The attempt's ``Progress`` service: thread-safe to report, delivered on the tick."""

    __slots__ = ("_latest", "_pending")

    def __init__(self) -> None:
        self._latest: float | None = None
        self._pending = False

    def report(self, fraction: float) -> None:
        """Record the latest fraction; the subscriber hears it at the next tick."""
        if not isinstance(fraction, (int, float)) or not 0.0 <= fraction <= 1.0:
            raise ValueError(
                f"progress must be a fraction from 0.0 to 1.0, not {fraction!r}"
            )
        self._latest = float(fraction)
        self._pending = True

    @property
    def latest(self) -> float | None:
        return self._latest

    def take(self) -> float | None:
        """Return the fraction to deliver now, or ``None`` when nothing is new."""
        if not self._pending:
            return None
        self._pending = False
        return self._latest


class _Cancellation:
    """The attempt's read-only ``Cancellation`` service."""

    __slots__ = ("_attempt",)

    def __init__(self, attempt: _Attempt) -> None:
        self._attempt = attempt

    def is_cancelled(self) -> bool:
        job = self._attempt._job
        return job is not None and job.cancellation.is_cancelled()


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
    def status(self) -> JobStatus:
        return _STATUS_OF_STATE[self.job.state]

    @property
    def error(self) -> BaseException | None:
        return self.job.error if self.status is JobStatus.FAILED else None

    def outcome(self) -> object:
        """Return the result, or raise what stands in its place (TASK-46)."""
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
        # finished job leaves nothing behind on it (TASK-47).
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
        self.job.cancel()

    def abandoned(self) -> None:
        """The plugin is gone: the scheduler abandons the job; nobody is called."""
        self._owner_closed = True
        self.detach()
        self.settled.set()


_TICK_IN_PROGRESS = "a tick is already in progress on this thread"

_TERMINAL_EVENT: dict[JobStatus, JobEvent] = {
    JobStatus.SUCCEEDED: "success",
    JobStatus.FAILED: "failure",
    JobStatus.CANCELLED: "cancelled",
}


async def _run_attempt(attempt: _Attempt, cls: type, inputs: object) -> object:
    """The coroutine the scheduler drives: construct, run, check the result type."""
    attempt.scope.ensure_open()
    context = JobContext(
        progress=attempt.progress,
        cancellation=_Cancellation(attempt),
        scope=attempt.scope,
        workers=attempt.runtime.workers,
        network=attempt.runtime.network,
    )
    outcome = cls(context).run(inputs)
    if inspect.isawaitable(outcome):
        outcome = await outcome
    description = attempt.description
    if not isinstance(outcome, description.result_type):
        raise QgisSdkDeclarationError(
            f"{description.id}: run returned {type_name(type(outcome))}, not the "
            f"declared {type_name(description.result_type)}"
        )
    return outcome


# -- handles ------------------------------------------------------------------------


class JobHandle:
    """What ``delay`` returns: identity, state, cancellation, outcome, subscriptions.

    Everything on a handle is safe to call from the driving thread. ``cancel``
    and the read-only properties are safe from any thread; ``get`` is for any
    thread *but* the GUI thread.
    """

    __slots__ = ("_attempt",)

    def __init__(self, attempt: _Attempt) -> None:
        self._attempt = attempt

    # -- identity and state

    @property
    def id(self) -> str:
        """The logical job id: ``<declared id>#<submission number>``."""
        return self._attempt.id

    @property
    def attempt(self) -> int:
        """The attempt number; always ``1`` until an explicit retry policy exists."""
        return self._attempt.attempt

    @property
    def description(self) -> JobDescription:
        """The declaration this job was submitted from."""
        return self._attempt.description

    @property
    def status(self) -> JobStatus:
        """The current state; ``cancelled`` only once cancellation is acknowledged."""
        return self._attempt.status

    @property
    def cancel_requested(self) -> bool:
        """Whether anyone asked the job to stop, acknowledged or not."""
        return self._attempt.job.cancellation.is_cancelled()

    @property
    def owner_closed(self) -> bool:
        """Whether the owning scope was disposed, detaching every callback."""
        return self._attempt.owner_closed

    @property
    def progress(self) -> float | None:
        """The latest fraction reported, or ``None`` before any report."""
        return self._attempt.progress.latest

    @property
    def result(self) -> Any:
        """The typed result of a succeeded job.

        A failed job raises its own exception (the one ``error`` returns), a
        cancelled job raises ``QgisSdkJobCancelledError``, and a job that has
        not settled raises ``QgisSdkJobNotSettledError`` - the same reading
        :meth:`get` gives, without the wait.
        """
        return self._attempt.outcome()

    @property
    def error(self) -> BaseException | None:
        """The exception of a failed job, else ``None``."""
        return self._attempt.error

    # -- control

    def cancel(self) -> bool:
        """Request cancellation; return whether the job was still active."""
        return self._attempt.job.cancel()

    def get(self, timeout: float | None = None) -> Any:
        """Block until the job settles and return its result.

        Refused on the GUI thread (``QgisSdkJobWaitRefusedError``) - that
        thread is the one delivering the outcome. Elsewhere it waits up to
        ``timeout`` seconds, raises ``QgisSdkJobNotSettledError`` when that
        runs out, re-raises a failure, and raises ``QgisSdkJobCancelledError``
        for a cancelled job.
        """
        attempt = self._attempt
        if attempt.runtime.gui_thread():
            raise QgisSdkJobWaitRefusedError(attempt.id)
        attempt.settled.wait(timeout)
        return attempt.outcome()

    # -- subscriptions

    def on_progress(
        self, callback: Callable[[float], None], *, owner: ResourceScope | None = None
    ) -> JobSubscription:
        """Hear the latest fraction once per tick it changed; replays the current one."""
        return self._attempt.subscribe("progress", callback, owner)

    def on_success(
        self, callback: Callable[[Any], None], *, owner: ResourceScope | None = None
    ) -> JobSubscription:
        """Hear the typed result exactly once."""
        return self._attempt.subscribe("success", callback, owner)

    def on_failure(
        self,
        callback: Callable[[BaseException], None],
        *,
        owner: ResourceScope | None = None,
    ) -> JobSubscription:
        """Hear the exception exactly once."""
        return self._attempt.subscribe("failure", callback, owner)

    def on_cancelled(
        self, callback: Callable[[], None], *, owner: ResourceScope | None = None
    ) -> JobSubscription:
        """Hear acknowledged cancellation exactly once."""
        return self._attempt.subscribe("cancelled", callback, owner)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, JobHandle) and other._attempt is self._attempt

    def __hash__(self) -> int:
        return hash(id(self._attempt))

    def __repr__(self) -> str:
        return f"JobHandle({self.id!r}, {self.status.value})"


# -- the service ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BoundJob:
    """A job class bound to an owner; ``delay`` submits one attempt."""

    description: JobDescription
    cls: type
    service: JobService = field(repr=False)

    def delay(self, inputs: object) -> JobHandle:
        """Submit one attempt with ``inputs``; no author code runs yet."""
        return self.service._submit(self, inputs)


@dataclass(eq=False)
class _Runtime:
    """The plugin-wide state every ``JobService`` over one scheduler shares.

    Built once by the plugin's service and handed to each view-derived one, so
    a derived service is a complete object with the same attributes as its
    parent (TASK-48) rather than a shell that reaches into the root.
    """

    scope: ResourceScope
    scheduler: StepScheduler
    workers: Workers | None
    network: Network | None
    gui_thread: Callable[[], bool]
    on_fault: Callable[[JobFault], None] | None
    attempts: dict[str, _Attempt] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    faults: list[JobFault] = field(default_factory=list)
    owner_hooks: dict[ResourceScope, dict[JobSubscription, None]] = field(
        default_factory=dict
    )
    ticking: bool = False

    def fault(self, fault: JobFault) -> None:
        self.faults.append(fault)
        if self.on_fault is not None:
            self.on_fault(fault)

    def deliver_all(self) -> None:
        for attempt in tuple(self.attempts.values()):
            attempt.deliver()

    def abandon_all(self) -> None:
        for attempt in tuple(self.attempts.values()):
            attempt.abandoned()
        self.attempts.clear()

    # -- explicit subscription owners (TASK-47)

    def add_owner_hook(
        self, owner: ResourceScope, subscription: JobSubscription
    ) -> None:
        """Dispose ``subscription`` when ``owner`` closes; one hook per owner scope."""
        live = self.owner_hooks.get(owner)
        if live is None:
            live = self.owner_hooks[owner] = {}
            owner.on_close(lambda: self._owner_hook_fired(owner))
        live[subscription] = None

    def release_owner_hook(
        self, owner: ResourceScope, subscription: JobSubscription
    ) -> None:
        live = self.owner_hooks.get(owner)
        if live is not None:
            live.pop(subscription, None)

    def _owner_hook_fired(self, owner: ResourceScope) -> None:
        for subscription in tuple(self.owner_hooks.pop(owner, ())):
            subscription.dispose()


class JobService:
    """``ctx.jobs``: binds job classes to an owner and delivers their outcomes.

    One *root* service exists per plugin runtime; it owns the step scheduler
    over the plugin scope. :meth:`scoped` derives a view-owned service over a
    child scope that shares the same scheduler, which is how view ownership
    works: a view's service closes with the view, the plugin's scheduler does
    not. ``parent`` on a derived service is the explicit route to
    plugin-lifetime work from a view.

    ``gui_thread`` answers "is the calling thread the GUI thread?" for
    :meth:`JobHandle.get`; the default says yes for the interpreter's main
    thread, which is where QGIS runs its GUI.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        workers: Workers | None = None,
        network: Network | None = None,
        gui_thread: Callable[[], bool] | None = None,
        on_fault: Callable[[JobFault], None] | None = None,
        max_steps_per_job: int | None = None,
    ) -> None:
        scope.ensure_open()
        scheduler = (
            StepScheduler(scope)
            if max_steps_per_job is None
            else StepScheduler(scope, max_steps_per_job=max_steps_per_job)
        )
        runtime = _Runtime(
            scope=scope,
            scheduler=scheduler,
            workers=workers,
            network=network,
            gui_thread=gui_thread if gui_thread is not None else _main_thread,
            on_fault=on_fault,
        )
        self._bind(scope, runtime, parent=None)
        # Registered after the scheduler's own disposal hook, so it runs before
        # it: every subscription is gone before any job is abandoned.
        scope.on_close(runtime.abandon_all)
        # A development host asks the plugin scope before replacing the
        # revision; the scheduler's answer is the one that counts (decision-21).
        scope.on_quiesce(self.quiesce, resume=self.resume)

    def _bind(
        self, scope: ResourceScope, runtime: _Runtime, *, parent: JobService | None
    ) -> None:
        """Set every attribute a service has; the one constructor both routes use."""
        self._scope = scope
        self._runtime = runtime
        self._parent = parent

    @classmethod
    def _derived(cls, parent: JobService, scope: ResourceScope) -> JobService:
        scope.ensure_open()
        service = cls.__new__(cls)
        service._bind(scope, parent._runtime, parent=parent)
        scope.on_close(service._owner_disposed)
        return service

    # -- shape

    @property
    def scope(self) -> ResourceScope:
        """The scope that owns the jobs this service submits."""
        return self._scope

    @property
    def parent(self) -> JobService | None:
        """The service this one was derived from, or ``None`` for the plugin's."""
        return self._parent

    def scoped(self, scope: ResourceScope) -> JobService:
        """Derive a service whose jobs are owned by ``scope`` (a view's, usually)."""
        return JobService._derived(self, scope)

    @property
    def active(self) -> tuple[JobHandle, ...]:
        """Handles not yet settled and delivered, in submission order.

        The plugin's service sees every job; a derived service sees its own.
        """
        return tuple(
            JobHandle(attempt)
            for attempt in self._runtime.attempts.values()
            if attempt.owner is self or self._parent is None
        )

    @property
    def faults(self) -> tuple[JobFault, ...]:
        """Subscriber callbacks that raised, oldest first."""
        return tuple(self._runtime.faults)

    # -- submission

    def bind(self, cls: type) -> BoundJob:
        """Bind a ``@job`` class to this owner; the declaration is checked now."""
        self._scope.ensure_open()
        return BoundJob(describe_job(cls), cls, self)

    def _submit(self, bound: BoundJob, inputs: object) -> JobHandle:
        self._scope.ensure_open()
        description = bound.description
        if not isinstance(inputs, description.inputs_type):
            expected = type_name(description.inputs_type)
            problem = f"inputs must be {expected}, not {type_name(type(inputs))}"
            raise QgisSdkJobRejectedError(description.id, [problem])
        runtime = self._runtime
        number = runtime.counters.get(description.id, 0) + 1
        runtime.counters[description.id] = number
        attempt = _Attempt(
            runtime=runtime,
            owner=self,
            description=description,
            logical_id=f"{description.id}#{number}",
        )
        coroutine = _run_attempt(attempt, bound.cls, inputs)
        try:
            attempt._job = runtime.scheduler.submit(coroutine)
        except BaseException:
            attempt.scope.close()
            raise
        runtime.attempts[attempt.id] = attempt
        return JobHandle(attempt)

    # -- driving

    def tick(self) -> int:
        """Advance every job one bounded step and deliver what changed.

        Call this from the thread that owns the GUI; it is the only thread on
        which subscribers run. Returns the number of author steps taken.

        A tick entered while another is on the stack - a job or a subscriber
        opened a modal dialog whose nested event loop fired the host timer -
        does nothing and returns ``0``; the outer tick finishes when the
        dialog closes (TASK-44). Re-stepping a job that is mid-step would fail
        it, and an exception here would escape a Qt slot.
        """
        runtime = self._runtime
        if runtime.ticking:
            return 0
        runtime.ticking = True
        try:
            steps = runtime.scheduler.tick()
            runtime.deliver_all()
        finally:
            runtime.ticking = False
        return steps

    def quiesce(self, *, max_ticks: int | None = None) -> QuiesceOutcome:
        """Ask every job to stop and look for a safe replacement point.

        Refused outright from inside a tick, for the same reason a nested tick
        is ignored; the blocker names the condition.
        """
        runtime = self._runtime
        if runtime.ticking:
            return QuiesceOutcome(refused=True, blockers=(_TICK_IN_PROGRESS,))
        runtime.ticking = True
        try:
            outcome = (
                runtime.scheduler.quiesce()
                if max_ticks is None
                else runtime.scheduler.quiesce(max_ticks=max_ticks)
            )
            runtime.deliver_all()
        finally:
            runtime.ticking = False
        return self._named(outcome)

    def resume(self) -> None:
        """Accept new work again after a refused replacement."""
        self._runtime.scheduler.resume()

    def _named(self, outcome: QuiesceOutcome) -> QuiesceOutcome:
        """Name blockers by the handle id authors see, not the scheduler's."""
        if not outcome.blockers:
            return outcome
        names = {
            attempt._job.id: attempt.id
            for attempt in self._runtime.attempts.values()
            if attempt._job is not None
        }
        blockers = []
        for blocker in outcome.blockers:
            for number, handle_id in names.items():
                prefix = f"job {number} "
                if blocker.startswith(prefix):
                    blocker = f"job {handle_id} " + blocker[len(prefix) :]
                    break
            blockers.append(blocker)
        return QuiesceOutcome(refused=outcome.refused, blockers=tuple(blockers))

    # -- ownership hooks

    def _owner_disposed(self) -> None:
        for attempt in tuple(self._runtime.attempts.values()):
            if attempt.owner is self:
                attempt.owner_disposed()
