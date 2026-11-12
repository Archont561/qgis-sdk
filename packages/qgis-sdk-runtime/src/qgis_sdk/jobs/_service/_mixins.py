from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.core.scheduling import QuiesceOutcome
from qgis_sdk.jobs._attempt import (
    _NOT_THE_DRIVING_THREAD,
    _TICK_IN_PROGRESS,
)
from qgis_sdk.jobs._authoring import (
    check_arguments,
    describe_job,
)
from qgis_sdk.jobs._handles import BoundJob, JobHandle, as_handles
from qgis_sdk.jobs._ownership import INVOKING_SCOPE
from qgis_sdk.jobs._registry import JobRegistry
from qgis_sdk.jobs._subscriptions import JobFault
from qgis_sdk.models import (
    QgisSdkJobRejectedError,
)

from ._init_state import After, Runtime, submit_phase1

if TYPE_CHECKING:
    from qgis_sdk.jobs._service._service import JobService


class JobServiceMixin1:
    def _bind(
        self,
        scope: ResourceScope,
        runtime: Runtime,
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

    def _owner(self) -> JobService:
        """The service a submission belongs to, given who is invoking it."""
        if self._pinned or self._parent is not None:
            return self
        scope = INVOKING_SCOPE.get()
        if scope is None or scope is self._scope or scope.closed:
            return self
        if not belongs_to(scope, self._scope):
            # Someone else's dispatch (another plugin, a host request with no
            # scope of ours): plugin lifetime is the safe reading.
            return self
        return self.scoped(scope)


class JobServiceMixin2:
    def delay(self, function: Callable[..., Any], /, **arguments: Any) -> JobHandle:
        """``bind(function).delay(**arguments)`` in one call."""
        return self.bind(function).delay(**arguments)

    def after(self, *handles: JobHandle) -> After:
        """Submit work that runs only after the jobs in ``handles`` succeeded.

        ``ctx.jobs.after(first).bind(second).delay(a=1)`` - or, with a declared
        name, ``ctx.jobs.after(first).<name>.delay(a=1)``. The ordering is
        enforced before the dependent body is handed to a worker, so it holds
        for every backend; a prerequisite that fails or is cancelled fails the
        dependent job with ``QgisSdkJobPrerequisiteError``.
        """
        return After(self, as_handles(handles))

    def _submit(self, bound: BoundJob, arguments: dict[str, Any]) -> JobHandle:
        self._scope.ensure_open()
        description = bound.description
        problems = check_arguments(description, arguments)
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
        return submit_phase1(arguments, bound, description, runtime, self)

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


def belongs_to(scope: ResourceScope, ancestor: ResourceScope) -> bool:
    """Whether ``scope`` is ``ancestor`` or one of its descendants."""
    current: ResourceScope | None = scope
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False
