"""The service: :class:`JobService` over the step scheduler, ticked by the host."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.core.scheduling import QuiesceOutcome, StepScheduler
from qgis_sdk.jobs._attempt import _TICK_IN_PROGRESS, _Attempt, _run_attempt
from qgis_sdk.jobs._authoring import (
    _check_arguments,
    _main_thread,
    describe_job,
)
from qgis_sdk.jobs._handles import BoundJob, JobHandle
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
    thread, which is where QGIS runs its GUI. ``workers``, ``network``,
    ``algorithms`` and ``project`` become the matching capabilities of every
    ``JobContext`` this service builds; a host passes the ones it has.
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

    def bind(self, function: Callable[..., Any]) -> BoundJob:
        """Bind a ``@job`` function to this owner; the declaration is checked now."""
        self._scope.ensure_open()
        return BoundJob(describe_job(function), function, self)

    def delay(self, function: Callable[..., Any], /, **arguments: Any) -> JobHandle:
        """``bind(function).delay(**arguments)`` in one call."""
        return self.bind(function).delay(**arguments)

    def _submit(self, bound: BoundJob, arguments: dict[str, Any]) -> JobHandle:
        self._scope.ensure_open()
        description = bound.description
        problems = _check_arguments(description, arguments)
        if problems:
            raise QgisSdkJobRejectedError(description.id, problems)
        runtime = self._runtime
        number = runtime.counters.get(description.id, 0) + 1
        runtime.counters[description.id] = number
        attempt = _Attempt(
            runtime=runtime,
            owner=self,
            description=description,
            logical_id=f"{description.id}#{number}",
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

        A tick entered while another is on the stack - a job or a subscriber
        opened a modal dialog whose nested event loop fired the host timer -
        does nothing and returns ``0``; the outer tick finishes when the
        dialog closes. Re-stepping a job that is mid-step would fail
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
