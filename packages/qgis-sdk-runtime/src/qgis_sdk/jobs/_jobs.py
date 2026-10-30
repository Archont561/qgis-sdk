"""``ctx.jobs``: the plugin's named jobs, submitted through one owner.

What an action writes (decision-65)::

    handle = self.ctx.jobs.add.delay(left=1, right=2)
    handle.on_progress(self.bar.setValue)
    handle.on_success(self.refresh)

There is no ``bind`` here on purpose: a job is reached by the name the plugin
declared, and everything submission could get wrong - an unknown name, a
missing input, a value of the wrong type - is refused before any worker sees
it. ``bind`` and the function-passing ``delay`` remain on
:class:`~qgis_sdk.jobs.JobService`, which is what a host and a test drive;
author code never needs them.

Which owner the work belongs to is fixed by *which facade* is used, not by a
mutable global: ``ctx.jobs`` on a plugin context is plugin-lifetime work,
``ctx.jobs`` on a view's context is that view's, and ``ctx.jobs.plugin`` is the
explicit way for view code to ask for the plugin's lifetime. An action the
plugin instance handles - a toolbar button, a page's call - reaches a view's
facade through the runtime's per-dispatch owner, so a view-launched action
submits view-owned work without the handler having to say so (decision-65 §3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from qgis_sdk.core import ResourceScope
from qgis_sdk.jobs._authoring import JobDescription
from qgis_sdk.jobs._handles import BoundJob, JobHandle, as_handles
from qgis_sdk.jobs._registry import JobRegistry
from qgis_sdk.jobs._subscriptions import JobFault, JobSubscription

if TYPE_CHECKING:
    from qgis_sdk.jobs._service import JobService

__all__ = ["Jobs"]


class Jobs:
    """The named jobs of one plugin, submitted on behalf of one owner.

    ``service`` is a :class:`~qgis_sdk.jobs.JobService`: the plugin's own for
    ``PluginContext.jobs``, a view-scoped one for ``UiContext.jobs``. The facade
    adds nothing to the engine but the names, so ``ctx.jobs.<name>`` is a
    :class:`~qgis_sdk.jobs.BoundJob` and the rest reads the same whichever
    context it came from.
    """

    __slots__ = ("_service",)

    def __init__(self, service: JobService) -> None:
        self._service = service

    # -- what is declared

    @property
    def registry(self) -> JobRegistry:
        """The validated names this plugin declares."""
        return self._service.registry

    @property
    def names(self) -> tuple[str, ...]:
        """The declared names, in declaration order: what ``ctx.jobs.<name>`` takes."""
        return self.registry.names

    def describe(self, name: str) -> JobDescription:
        """The declared description of ``name``: its title, inputs and result."""
        return self.registry.description(name)

    def __len__(self) -> int:
        return len(self.registry)

    def __iter__(self) -> Iterator[str]:
        return iter(self.registry)

    def __contains__(self, name: object) -> bool:
        return name in self.registry

    # -- submitting

    def __getattr__(self, name: str) -> BoundJob:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._service, name)

    def __getitem__(self, name: str) -> BoundJob:
        return getattr(self._service, name)

    def after(self, *handles: JobHandle) -> OrderedJobs:
        """Name jobs ordered behind work already submitted.

        ``ctx.jobs.after(first).second.delay(a=1)``: the second body is not
        handed to a worker until the first succeeded, and a first job that
        failed or was cancelled fails the second one with
        ``QgisSdkJobPrerequisiteError`` instead of running it.
        """
        return OrderedJobs(self, as_handles(handles))

    # -- the owner

    @property
    def scope(self) -> ResourceScope:
        """The scope that owns work submitted through this facade."""
        return self._service.scope

    @property
    def plugin(self) -> Jobs:
        """The same names, submitted with the plugin's lifetime.

        The explicit opt-in decision-65 §3 asks for: inside a view, ``delay``
        after the view closes would be cancelled with it, so work that must
        outlive the window says so here.
        """
        return Jobs(self._service.plugin)

    def scoped(self, scope: ResourceScope) -> Jobs:
        """The same names, submitted on behalf of ``scope`` (a view's, usually)."""
        return Jobs(self._service.scoped(scope))

    # -- what is running

    @property
    def active(self) -> tuple[JobHandle, ...]:
        """Handles this owner submitted that are not settled yet, oldest first."""
        return self._service.active

    @property
    def faults(self) -> tuple[JobFault, ...]:
        """Subscriber callbacks that raised, oldest first."""
        return self._service.faults

    def watch(
        self,
        handle: JobHandle,
        *,
        on_progress: Callable[[float], None] | None = None,
        on_success: Callable[[object], None] | None = None,
        on_failure: Callable[[BaseException], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
    ) -> tuple[JobSubscription, ...]:
        """Subscribe callbacks to ``handle`` for this owner's lifetime.

        The one call a native surface needs for the four events
        ``JobHandle`` offers separately: each callback is owned by this
        facade's scope, so a view that closes stops hearing about the job
        before anything else runs. A handle that already settled replays
        once, immediately.
        """
        owner = self._service.scope
        subscriptions: list[JobSubscription] = []
        if on_progress is not None:
            subscriptions.append(handle.on_progress(on_progress, owner=owner))
        if on_success is not None:
            subscriptions.append(handle.on_success(on_success, owner=owner))
        if on_failure is not None:
            subscriptions.append(handle.on_failure(on_failure, owner=owner))
        if on_cancelled is not None:
            subscriptions.append(handle.on_cancelled(on_cancelled, owner=owner))
        return tuple(subscriptions)

    def __repr__(self) -> str:
        names = ", ".join(self.names) or "none"
        return f"<jobs of {self._service.scope!r}: {names}>"


class OrderedJobs:
    """``ctx.jobs.after(...)``: the same names, with an ordering baked in."""

    __slots__ = ("_handles", "_jobs")

    def __init__(self, jobs: Jobs, handles: tuple[JobHandle, ...]) -> None:
        self._jobs = jobs
        self._handles = handles

    @property
    def names(self) -> tuple[str, ...]:
        """The declared names, as :attr:`Jobs.names` gives them."""
        return self._jobs.names

    def __len__(self) -> int:
        return len(self._jobs)

    def __iter__(self) -> Iterator[str]:
        return iter(self._jobs)

    def __contains__(self, name: object) -> bool:
        return name in self._jobs

    def __getattr__(self, name: str) -> BoundJob:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._jobs, name).after(*self._handles)

    def __getitem__(self, name: str) -> BoundJob:
        return getattr(self._jobs, name).after(*self._handles)

    def __repr__(self) -> str:
        ids = ", ".join(handle.id for handle in self._handles)
        return f"<jobs after ({ids})>"
