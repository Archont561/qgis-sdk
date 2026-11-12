from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict, Unpack

from qgis_sdk.core import ResourceScope
from qgis_sdk.jobs._handles import BoundJob
from qgis_sdk.jobs._registry import JobRegistry
from qgis_sdk.jobs._subscriptions import JobFault
from qgis_sdk.services import Algorithms, Network, Project, Workers

from ._init_state import init_facts212345678, init_setup2
from ._mixins import JobServiceMixin1, JobServiceMixin2


class JobService(JobServiceMixin1, JobServiceMixin2):
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

    def __init__(self, scope: ResourceScope, **options: Unpack[_InitOptions1]) -> None:
        values = _InitValues1(**options)
        scheduler = init_setup2(values.max_steps_per_job, scope)
        init_facts212345678(
            algorithms=values.algorithms,
            gui_thread=values.gui_thread,
            network=values.network,
            on_fault=values.on_fault,
            project=values.project,
            registry=values.registry,
            scheduler=scheduler,
            scope=scope,
            self=self,
            workers=values.workers,
        )

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


class _InitOptions1(TypedDict, total=False):
    workers: Workers | None
    network: Network | None
    algorithms: Algorithms | None
    project: Project | None
    gui_thread: Callable[[], bool] | None
    on_fault: Callable[[JobFault], None] | None
    max_steps_per_job: int | None
    registry: JobRegistry | None


@dataclass(frozen=True, slots=True)
class _InitValues1:
    workers: Workers | None = None
    network: Network | None = None
    algorithms: Algorithms | None = None
    project: Project | None = None
    gui_thread: Callable[[], bool] | None = None
    on_fault: Callable[[JobFault], None] | None = None
    max_steps_per_job: int | None = None
    registry: JobRegistry | None = None
