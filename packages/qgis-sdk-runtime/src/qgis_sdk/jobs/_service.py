"""The service: :class:`JobService` over the step scheduler, ticked by the host."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.core.scheduling import QuiesceOutcome, StepScheduler
from qgis_sdk.jobs._attempt import (
    _NOT_THE_DRIVING_THREAD,
    _TICK_IN_PROGRESS,
    _Attempt,
    _run_attempt,
)
from qgis_sdk.jobs._authoring import (
    _check_arguments,
    _main_thread,
    describe_job,
)
from qgis_sdk.jobs._handles import BoundJob, JobHandle, as_handles
from qgis_sdk.jobs._ownership import INVOKING_SCOPE
from qgis_sdk.jobs._registry import JobRegistry
from qgis_sdk.jobs._subscriptions import JobFault, JobSubscription
from qgis_sdk.models import (
    QgisSdkJobRejectedError,
)
from qgis_sdk.services import Algorithms, Network, Project, Workers

# -- the service ------------------------------------------------------------------


@dataclass(eq=False)
class _Runtime:
    """The plugin-wide state every ``JobService`` over one scheduler shares.

    Built once by the plugin's service and handed to each view-derived one, so
    a derived service is a complete object with the same attributes as its
    parent rather than a shell that reaches into the root.
    """

    scope: ResourceScope
    scheduler: StepScheduler
    workers: Workers | None
    network: Network | None
    algorithms: Algorithms | None
    project: Project | None
    gui_thread: Callable[[], bool]
    on_fault: Callable[[JobFault], None] | None
    registry: JobRegistry = field(default_factory=JobRegistry.empty)
    driving_thread: int = field(default_factory=threading.get_ident)
    attempts: dict[str, _Attempt] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    faults: list[JobFault] = field(default_factory=list)
    owner_hooks: dict[ResourceScope, dict[JobSubscription, None]] = field(
        default_factory=dict
    )
    children: dict[ResourceScope, JobService] = field(default_factory=dict)
    pinned: JobService | None = None
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

    # -- explicit subscription owners

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


class _After:
    """``job_service.after(handles)``: the same service, with an ordering baked in.

    A thin view rather than a second service: every name a submitted job can be
    reached by - ``bind``, ``delay`` and the declared-name attributes TASK-116
    adds - carries the prerequisites, so ordering composes with however the job
    is submitted.
    """

    __slots__ = ("_prerequisites", "_service")

    def __init__(self, service: JobService, prerequisites: tuple[JobHandle, ...]):
        self._service = service
        self._prerequisites = prerequisites

    def bind(self, function: Callable[..., Any]) -> BoundJob:
        """Bind a job, ordered behind the prerequisites."""
        return self._service.bind(function).after(*self._prerequisites)

    def delay(self, function: Callable[..., Any], /, **arguments: Any) -> JobHandle:
        """``bind(function).delay(**arguments)``, ordered behind the prerequisites."""
        return self.bind(function).delay(**arguments)

    def __getattr__(self, name: str) -> Any:
        """Reach a declared job by name (TASK-116), ordered behind the prerequisites."""
        bound = getattr(self._service, name)
        if isinstance(bound, BoundJob):
            return bound.after(*self._prerequisites)
        return bound

    def __repr__(self) -> str:
        ids = ", ".join(handle.id for handle in self._prerequisites)
        return f"<jobs after {ids}>"


class JobService:
    """``ctx.jobs``: binds job functions to an owner and delivers their outcomes.

    One *root* service exists per plugin runtime; it owns the step scheduler
    over the plugin scope. :meth:`scoped` derives a view-owned service over a
    child scope that shares the same scheduler, which is how view ownership
    works: a view's service closes with the view, the plugin's scheduler does
    not. ``parent`` on a derived service is the explicit route to
    plugin-lifetime work from a view.

    ``gui_thread`` answers "is the calling thread the GUI thread?" for
    :meth:`JobHandle.get`; the default says yes for the interpreter's main
    thread, which is where QGIS runs its GUI. ``workers`` is required to submit
    at all: since 0.9.0 a job body runs in its entirety on a worker
    (decision-65), so a service without one refuses every submission rather
    than running author code here. The ``WorkerContext`` a body receives is
    built per attempt with progress and cancellation only; ``network``,
    ``algorithms`` and ``project`` stay on this side of the seam.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        workers: Workers | None = None,
        network: Network | None = None,
        algorithms: Algorithms | None = None,
        project: Project | None = None,
        gui_thread: Callable[[], bool] | None = None,
        on_fault: Callable[[JobFault], None] | None = None,
        max_steps_per_job: int | None = None,
        registry: JobRegistry | None = None,
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
            algorithms=algorithms,
            project=project,
            gui_thread=gui_thread if gui_thread is not None else _main_thread,
            on_fault=on_fault,
            registry=registry if registry is not None else JobRegistry.empty(),
        )
        self._bind(scope, runtime, parent=None)
        # Registered after the scheduler's own disposal hook, so it runs before
        # it: every subscription is gone before any job is abandoned.
        scope.on_close(runtime.abandon_all)
        # A development host asks the plugin scope before replacing the
        # revision; the scheduler's answer is the one that counts (decision-21).
        scope.on_quiesce(self.quiesce, resume=self.resume)

    def _bind(
        self,
        scope: ResourceScope,
        runtime: _Runtime,
        *,
        parent: JobService | None,
        pinned: bool = False,
    ) -> None:
        """Set every attribute a service has; the one constructor both routes use."""
        self._scope = scope
        self._runtime = runtime
        self._parent = parent
        self._pinned = pinned

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

    @property
    def registry(self) -> JobRegistry:
        """The plugin's validated job names (decision-65 §2)."""
        return self._runtime.registry

    @property
    def plugin(self) -> JobService:
        """The plugin-lifetime service, whatever service this is asked of.

        ``ctx.jobs.plugin`` is how view code says "this one outlives the
        window": the returned service submits as the plugin and never falls
        back to the invoking view.
        """
        runtime = self._runtime
        if runtime.pinned is None:
            pinned = type(self).__new__(type(self))
            pinned._bind(self._root()._scope, runtime, parent=None, pinned=True)
            runtime.pinned = pinned
        return runtime.pinned

    def scoped(self, scope: ResourceScope) -> JobService:
        """Derive a service whose jobs are owned by ``scope`` (a view's, usually).

        One service per scope, so a scope that opens and closes does not
        accumulate copies and ``active`` answers the same either way.
        """
        cached = self._runtime.children.get(scope)
        if cached is not None:
            return cached
        service = type(self)._derived(self, scope)
        self._runtime.children[scope] = service
        return service

    def request_scoped(self, scope: ResourceScope) -> JobService:
        """Derive a service whose jobs die with ``scope`` - one request's, on the server.

        This is :meth:`scoped` with the other disposal rule. A view's jobs are
        cancelled and then report what the worker did; a QGIS Server request has
        no pump that could ever deliver that report, so closing ``scope``
        *abandons* its jobs instead (decision-52): every handle reads
        ``JobStatus.CANCELLED`` at once, a worker still running is asked to
        stop, and no callback runs. Work that must outlive the request is
        submitted through ``ctx.jobs.plugin``.

        Nothing is cached - a request scope exists once, so a second call is a
        second derivation - and the caller closes the scope when the response is
        sent, which is the abandonment.
        """
        scope.ensure_open()
        service = type(self).__new__(type(self))
        service._bind(scope, self._runtime, parent=self)
        scope.on_close(service._owner_abandoned)
        return service

    def _root(self) -> JobService:
        """This service, or the plugin's one at the top of the chain."""
        service = self
        while service._parent is not None:
            service = service._parent
        return service

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

    def bind(self, function: Callable[..., Any]) -> BoundJob:
        """Bind a ``@job`` function to this owner; the declaration is checked now.

        The owner is resolved per call (decision-65 §3): a plugin-level service
        whose call arrives from a view's dispatch submits that view's work, so
        an action handler reads its own plugin context and still hands the
        window the lifetime it answers to. A host driving its own dispatch
        sets :data:`~qgis_sdk.jobs._ownership.INVOKING_SCOPE` the same way.
        """
        self._scope.ensure_open()
        owner = self._owner()
        if owner is not self:
            return owner.bind(function)
        return BoundJob(describe_job(function), function, self)

    def __getattr__(self, name: str) -> BoundJob:
        """Reach a declared job by name: ``service.add`` is what ``ctx.jobs.add`` is.

        Only the names the plugin declared exist here; anything else is an
        ``AttributeError`` naming what it does have, so a typo never looks
        like a job that failed to start.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        runtime = self.__dict__.get("_runtime")
        if runtime is None:
            raise AttributeError(name)
        # A declared name is a dictionary read: the description was validated
        # when the plugin started, so submission neither imports nor inspects
        # anything (decision-65 §2).
        description = runtime.registry.description(name)
        owner = self._owner()
        if owner is not self:
            return owner.__getattr__(name)
        return BoundJob(description, runtime.registry.function(name), self)

    def _owner(self) -> JobService:
        """The service a submission belongs to, given who is invoking it."""
        if self._pinned or self._parent is not None:
            return self
        scope = INVOKING_SCOPE.get()
        if scope is None or scope is self._scope or scope.closed:
            return self
        if not _belongs_to(scope, self._scope):
            # Someone else's dispatch (another plugin, a host request with no
            # scope of ours): plugin lifetime is the safe reading.
            return self
        return self.scoped(scope)

    def delay(self, function: Callable[..., Any], /, **arguments: Any) -> JobHandle:
        """``bind(function).delay(**arguments)`` in one call."""
        return self.bind(function).delay(**arguments)

    def after(self, *handles: JobHandle) -> _After:
        """Submit work that runs only after the jobs in ``handles`` succeeded.

        ``ctx.jobs.after(first).bind(second).delay(a=1)`` - or, with a declared
        name, ``ctx.jobs.after(first).<name>.delay(a=1)``. The ordering is
        enforced before the dependent body is handed to a worker, so it holds
        for every backend; a prerequisite that fails or is cancelled fails the
        dependent job with ``QgisSdkJobPrerequisiteError``.
        """
        return _After(self, as_handles(handles))

    def _submit(self, bound: BoundJob, arguments: dict[str, Any]) -> JobHandle:
        self._scope.ensure_open()
        description = bound.description
        problems = _check_arguments(description, arguments)
        if problems:
            raise QgisSdkJobRejectedError(description.id, problems)
        runtime = self._runtime
        if runtime.workers is None:
            # Decision-65: a job body never runs on the driving thread. A host
            # without a worker backend refuses the submission instead of
            # quietly degrading to the behaviour 0.9.0 removed.
            raise QgisSdkJobRejectedError(
                description.id,
                [
                    (
                        "this host provides no worker backend, and a job body "
                        "never runs on the driving thread; give the host a "
                        "Workers service (Desktop supplies a QThreadPool) or run "
                        "the code directly"
                    )
                ],
            )
        number = runtime.counters.get(description.id, 0) + 1
        runtime.counters[description.id] = number
        attempt = _Attempt(
            runtime=runtime,
            owner=self,
            description=description,
            logical_id=f"{description.id}#{number}",
            prerequisites=bound.prerequisites,
        )
        coroutine = _run_attempt(attempt, bound.function, dict(arguments))
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

        A tick entered while another is on the stack - a subscriber opened a
        modal dialog whose nested event loop fired the host timer - does
        nothing and returns ``0``; the outer tick finishes when the dialog
        closes. So does a tick entered from any thread other than the one that
        built the service: since 0.9.0 a job body runs on a worker, so author
        code has no tick of its own to enter (decision-65).
        """
        runtime = self._runtime
        if runtime.ticking or threading.get_ident() != runtime.driving_thread:
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
        if threading.get_ident() != runtime.driving_thread:
            return QuiesceOutcome(refused=True, blockers=(_NOT_THE_DRIVING_THREAD,))
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
        self._runtime.children.pop(self._scope, None)
        for attempt in tuple(self._runtime.attempts.values()):
            if attempt.owner is self:
                attempt.owner_disposed()

    def _owner_abandoned(self) -> None:
        """The request is over: abandon its jobs instead of waiting for a report.

        The other half of :meth:`_owner_disposed`, chosen by
        :meth:`request_scoped`: nothing on the server will ever deliver these
        outcomes, so each attempt names itself cancelled and leaves the books.
        """
        self._runtime.children.pop(self._scope, None)
        for attempt in tuple(self._runtime.attempts.values()):
            if attempt.owner is self:
                attempt.cancelled_by_request()


def _belongs_to(scope: ResourceScope, ancestor: ResourceScope) -> bool:
    """Whether ``scope`` is ``ancestor`` or one of its descendants."""
    current: ResourceScope | None = scope
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False
