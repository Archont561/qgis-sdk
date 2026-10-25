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
    _hints,
    _Metadata,
    _metadata,
    _schema,
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


def _type_name(annotation: Any) -> str:
    return getattr(annotation, "__name__", str(annotation))


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


def job(*, id: str, title: str) -> Callable[[type[T]], type[T]]:
    """Attach job metadata without wrapping or constructing the class."""

    metadata = _metadata(id, title)

    def decorate(cls: type[T]) -> type[T]:
        if not inspect.isclass(cls):
            raise QgisSdkDeclarationError("@job requires a class")
        if _JOB_ATTRIBUTE in vars(cls):
            raise QgisSdkDeclarationError(f"{id}: duplicate @job declaration")
        setattr(cls, _JOB_ATTRIBUTE, metadata)
        return cls

    return decorate


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
                "type": _type_name(self.inputs_type),
                "schema": self.inputs_schema,
            },
            "result": {
                "type": _type_name(self.result_type),
                "schema": self.result_schema,
            },
        }


def describe_job(cls: type) -> JobDescription:
    """Inspect one decorated class without constructing it or calling ``run``."""
    if not inspect.isclass(cls) or _JOB_ATTRIBUTE not in vars(cls):
        raise QgisSdkDeclarationError("describe_job requires a class with @job")
    metadata = vars(cls)[_JOB_ATTRIBUTE]
    if not isinstance(metadata, _Metadata):
        raise QgisSdkDeclarationError("describe_job requires a class with @job")
    run = vars(cls).get("run")
    if not inspect.isfunction(run):
        raise QgisSdkDeclarationError(f"{metadata.id}: a job needs its own run method")
    parameters = list(inspect.signature(run).parameters.values())
    if len(parameters) != 2 or parameters[0].name != "self":
        raise QgisSdkDeclarationError(
            f"{metadata.id}: run takes self and exactly one typed inputs argument"
        )
    hints = _hints(run, f"job {metadata.id}")
    inputs_type = hints.get(parameters[1].name, inspect.Parameter.empty)
    result_type = hints.get("return", inspect.Signature.empty)
    if inputs_type is inspect.Parameter.empty:
        raise QgisSdkDeclarationError(f"{metadata.id}: run inputs must be annotated")
    if result_type is inspect.Signature.empty:
        raise QgisSdkDeclarationError(f"{metadata.id}: run must declare its result")
    return JobDescription(
        id=metadata.id,
        title=metadata.title,
        inputs_type=inputs_type,
        result_type=result_type,
        inputs_schema=_schema(inputs_type, f"{metadata.id}.inputs", result=False),
        result_schema=_schema(result_type, f"{metadata.id}.result", result=True),
        asynchronous=inspect.iscoroutinefunction(run),
    )


# -- subscriptions ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobFault:
    """A subscriber that raised; it was detached and the job carried on."""

    job_id: str
    event: JobEvent
    error: BaseException


class JobSubscription:
    """One disposable callback registration on a handle."""

    __slots__ = ("_active", "_attempt", "_callback", "_event")

    def __init__(self, attempt: _Attempt, event: JobEvent, callback: Callable) -> None:
        self._attempt = attempt
        self._event = event
        self._callback = callback
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
        root: JobService,
        owner: JobService,
        description: JobDescription,
        logical_id: str,
    ) -> None:
        self.root = root
        self.owner = owner
        self.description = description
        self.id = logical_id
        self.attempt = 1
        self.scope = root._scope.child()
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

    # -- subscriptions

    def subscribe(
        self, event: JobEvent, callback: Callable, owner: ResourceScope | None
    ) -> JobSubscription:
        if self.owner_closed:
            raise QgisSdkScopeClosedError()
        if owner is not None:
            owner.ensure_open()
        subscription = JobSubscription(self, event, callback)
        if self._replay(subscription):
            return subscription
        self._subscriptions[event][subscription] = None
        if owner is not None and owner is not self.owner._scope:
            owner.on_close(subscription.dispose)
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
            self.root._fault(JobFault(self.id, subscription.event, error))

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
        self.root._attempts.pop(self.id, None)
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
        workers=attempt.root._workers,
        network=attempt.root._network,
    )
    outcome = cls(context).run(inputs)
    if inspect.isawaitable(outcome):
        outcome = await outcome
    description = attempt.description
    if not isinstance(outcome, description.result_type):
        raise QgisSdkDeclarationError(
            f"{description.id}: run returned {_type_name(type(outcome))}, not the "
            f"declared {_type_name(description.result_type)}"
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
        """The typed result of a succeeded job; anything else is refused."""
        attempt = self._attempt
        if attempt.status is not JobStatus.SUCCEEDED:
            raise QgisSdkJobNotSettledError(attempt.id, attempt.status.value)
        return attempt.job.result

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
        if attempt.root._gui_thread():
            raise QgisSdkJobWaitRefusedError(attempt.id)
        if not attempt.settled.wait(timeout):
            raise QgisSdkJobNotSettledError(attempt.id, attempt.status.value)
        status = attempt.status
        if status is JobStatus.SUCCEEDED:
            return attempt.job.result
        if status is JobStatus.CANCELLED:
            raise QgisSdkJobCancelledError(attempt.job.id)
        error = attempt.job.error
        assert error is not None
        raise error

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
        self._scope = scope
        self._parent: JobService | None = None
        self._root: JobService = self
        self._workers = workers
        self._network = network
        self._gui_thread = gui_thread if gui_thread is not None else _main_thread
        self._on_fault = on_fault
        self._scheduler = (
            StepScheduler(scope)
            if max_steps_per_job is None
            else StepScheduler(scope, max_steps_per_job=max_steps_per_job)
        )
        self._attempts: dict[str, _Attempt] = {}
        self._counters: dict[str, int] = {}
        self._faults: list[JobFault] = []
        # Registered after the scheduler's own disposal hook, so it runs before
        # it: every subscription is gone before any job is abandoned.
        scope.on_close(self._abandon_all)

    @classmethod
    def _derived(cls, parent: JobService, scope: ResourceScope) -> JobService:
        scope.ensure_open()
        service = cls.__new__(cls)
        service._scope = scope
        service._parent = parent
        service._root = parent._root
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
        """Handles not yet settled and delivered, in submission order."""
        root = self._root
        return tuple(
            JobHandle(attempt)
            for attempt in root._attempts.values()
            if attempt.owner is self or self is root
        )

    @property
    def faults(self) -> tuple[JobFault, ...]:
        """Subscriber callbacks that raised, oldest first."""
        return tuple(self._root._faults)

    # -- submission

    def bind(self, cls: type) -> BoundJob:
        """Bind a ``@job`` class to this owner; the declaration is checked now."""
        self._scope.ensure_open()
        return BoundJob(describe_job(cls), cls, self)

    def _submit(self, bound: BoundJob, inputs: object) -> JobHandle:
        self._scope.ensure_open()
        description = bound.description
        if not isinstance(inputs, description.inputs_type):
            expected = _type_name(description.inputs_type)
            problem = f"inputs must be {expected}, not {_type_name(type(inputs))}"
            raise QgisSdkJobRejectedError(description.id, [problem])
        root = self._root
        number = root._counters.get(description.id, 0) + 1
        root._counters[description.id] = number
        attempt = _Attempt(
            root=root,
            owner=self,
            description=description,
            logical_id=f"{description.id}#{number}",
        )
        coroutine = _run_attempt(attempt, bound.cls, inputs)
        try:
            attempt._job = root._scheduler.submit(coroutine)
        except BaseException:
            attempt.scope.close()
            raise
        root._attempts[attempt.id] = attempt
        return JobHandle(attempt)

    # -- driving

    def tick(self) -> int:
        """Advance every job one bounded step and deliver what changed.

        Call this from the thread that owns the GUI; it is the only thread on
        which subscribers run. Returns the number of author steps taken.
        """
        root = self._root
        steps = root._scheduler.tick()
        for attempt in tuple(root._attempts.values()):
            attempt.deliver()
        return steps

    def quiesce(self, *, max_ticks: int | None = None) -> QuiesceOutcome:
        """Ask every job to stop and look for a safe replacement point."""
        root = self._root
        outcome = (
            root._scheduler.quiesce()
            if max_ticks is None
            else root._scheduler.quiesce(max_ticks=max_ticks)
        )
        for attempt in tuple(root._attempts.values()):
            attempt.deliver()
        return outcome

    def resume(self) -> None:
        """Accept new work again after a refused replacement."""
        self._root._scheduler.resume()

    # -- ownership hooks

    def _owner_disposed(self) -> None:
        for attempt in tuple(self._root._attempts.values()):
            if attempt.owner is self:
                attempt.owner_disposed()

    def _abandon_all(self) -> None:
        for attempt in tuple(self._attempts.values()):
            attempt.abandoned()
        self._attempts.clear()

    def _fault(self, fault: JobFault) -> None:
        self._faults.append(fault)
        if self._on_fault is not None:
            self._on_fault(fault)
