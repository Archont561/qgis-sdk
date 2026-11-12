"""The service: :class:`JobService` over the step scheduler, ticked by the host."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.core.scheduling import StepScheduler
from qgis_sdk.jobs._attempt import (
    _Attempt,
    run_attempt,
)
from qgis_sdk.jobs._authoring import (
    main_thread,
)
from qgis_sdk.jobs._handles import BoundJob, JobHandle
from qgis_sdk.jobs._registry import JobRegistry
from qgis_sdk.jobs._subscriptions import JobFault, JobSubscription
from qgis_sdk.services import Algorithms, Network, Project, Workers

if TYPE_CHECKING:
    from qgis_sdk.jobs._service._service import JobService


def init_setup2(max_steps_per_job, scope):
    scope.ensure_open()
    scheduler = (
        StepScheduler(scope)
        if max_steps_per_job is None
        else StepScheduler(scope, max_steps_per_job=max_steps_per_job)
    )
    return scheduler


def init_facts212345678(**values):
    _init_facts21234567(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts21234567(**values):
    _init_facts2123456(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts2123456(**values):
    _init_facts212345(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts212345(**values):
    _init_facts21234(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts21234(**values):
    _init_facts2123(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts2123(**values):
    _init_facts212(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts212(**values):
    _init_facts21(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts21(**values):
    _init_facts2(
        algorithms=values["algorithms"],
        gui_thread=values["gui_thread"],
        network=values["network"],
        on_fault=values["on_fault"],
        project=values["project"],
        registry=values["registry"],
        scheduler=values["scheduler"],
        scope=values["scope"],
        self=values["self"],
        workers=values["workers"],
    )


def _init_facts2(**values):
    runtime = Runtime(
        scope=values["scope"],
        scheduler=values["scheduler"],
        workers=values["workers"],
        network=values["network"],
        algorithms=values["algorithms"],
        project=values["project"],
        gui_thread=values["gui_thread"]
        if values["gui_thread"] is not None
        else main_thread,
        on_fault=values["on_fault"],
        registry=values["registry"]
        if values["registry"] is not None
        else JobRegistry.empty(),
    )
    _init_phase1(runtime, values["scope"], values["self"])


def _init_phase1(runtime, scope, self):
    self._bind(scope, runtime, parent=None)
    # Registered after the scheduler's own disposal hook, so it runs before
    # it: every subscription is gone before any job is abandoned.
    scope.on_close(runtime.abandon_all)
    # A development host asks the plugin scope before replacing the
    # revision; the scheduler's answer is the one that counts (decision-21).
    scope.on_quiesce(self.quiesce, resume=self.resume)


def submit_phase1(arguments, bound, description, runtime, self):
    number = runtime.counters.get(description.id, 0) + 1
    runtime.counters[description.id] = number
    attempt = _Attempt(
        runtime=runtime,
        owner=self,
        description=description,
        logical_id=f"{description.id}#{number}",
        prerequisites=bound.prerequisites,
    )
    coroutine = run_attempt(attempt, bound.function, dict(arguments))
    try:
        attempt._job = runtime.scheduler.submit(coroutine)
    except BaseException:
        attempt.scope.close()
        raise
    runtime.attempts[attempt.id] = attempt
    return JobHandle(attempt)


@dataclass(eq=False)
class Runtime:
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


class After:
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
