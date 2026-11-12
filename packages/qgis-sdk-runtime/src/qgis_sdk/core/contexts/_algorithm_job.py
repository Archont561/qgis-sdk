from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import (
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.services import (
    Algorithms,
    Cancellation,
    Network,
    Progress,
    Project,
    Workers,
)

from ._base import Capability, Context
from ._plugin_ui import AlgorithmServices


class AlgorithmContext(Context):
    """Execution-only capabilities for one Processing invocation.

    Built fresh for each invocation by :func:`qgis_sdk.algorithms.invoke` and
    thrown away afterwards (decision-11), and passed to the
    ``@provider.algorithm`` function as its first argument (decision-42), so
    no state carries from one run into the next. It is not a
    ``PluginContext``: no ``iface``, no dialogs, no GUI notifications - only
    what one execution legitimately needs. ``project`` is a capability so an
    algorithm that composes another through ``invoke`` can still add the
    result to the project when its host has one; ``network`` likewise.
    """

    __slots__ = (
        "_network",
        "_project",
        "algorithms",
        "cancellation",
        "progress",
        "scope",
    )

    _capability_names = ("project", "network")

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    algorithms: Algorithms
    project: Capability[Project] = Capability()
    network: Capability[Network] = Capability()

    def __init__(
        self,
        progress: Progress,
        cancellation: Cancellation,
        scope: ResourceScope,
        services: AlgorithmServices,
    ) -> None:
        self._assemble(
            progress=progress,
            cancellation=cancellation,
            scope=scope,
            algorithms=services.algorithms,
            **{f"_{name}": getattr(services, name) for name in self._capability_names},
        )


class WorkerContext:
    """The restricted context a ``@job`` body receives on its worker (decision-65).

    A job body runs in its entirety off the driving thread, so it is handed
    only what a worker may safely touch: ``progress`` and a cooperative
    ``cancellation``, both thread-safe by contract. Everything the driving
    thread owns - the project and its layers, the Processing algorithms, the
    interface, the surfaces, another worker pool - is absent, and reading it
    fails by name with the reason instead of returning ``None`` or a live
    object that would crash QGIS from a worker thread.

    This is a guard, not a sandbox. A body can still reach a module-level
    ``iface`` it imported itself, pass a live layer in as an argument, or call
    a helper that does either; ``qgis-sdk check`` names the imports it can see
    (TASK-117) and the runtime refuses what reaches the context, but neither
    proves thread safety. Prepare GUI state before submission and apply GUI
    updates in a callback, which is delivered on the driving thread.
    """

    __slots__ = ("cancellation", "progress")

    progress: Progress
    cancellation: Cancellation

    #: Names a driving-thread context carries and a worker does not, with the
    #: sentence the refusal shows.
    _REFUSED: ClassVar[dict[str, str]] = {
        "algorithms": (
            "Processing runs on the thread that owns the application; return a "
            "result and invoke it from the subscriber instead"
        ),
        "files": "file dialogs are GUI state; resolve a path before submitting",
        "iface": "the QGIS interface belongs to the driving thread",
        "layers": "layers are GUI-affine; pass plain values and re-read them on delivery",
        "layouts": (
            "print layouts belong to the project; ctx.layouts.export submits the "
            "render as its own job, and a job body cannot submit one"
        ),
        "network": "the network client suspends on the driving thread, not on a worker",
        "notifications": "the message bar is GUI state; report through the job outcome",
        "project": "the project service is owned by the driving thread",
        "scope": "the job's scope closes on delivery, on the driving thread",
        "ui": "surfaces are GUI state; open one from the driving thread",
        "view": "a view outlives no job and is not thread-safe",
        "workers": "the job body is already on a worker",
    }

    def __init__(self, progress: Progress, cancellation: Cancellation) -> None:
        object.__setattr__(self, "progress", progress)
        object.__setattr__(self, "cancellation", cancellation)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"WorkerContext is assembled once; {name!r} is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"WorkerContext is assembled once; {name!r} is read-only")

    def __getattr__(self, name: str) -> Any:
        """Refuse a driving-thread capability by name, never with a bare AttributeError.

        Only reached for names the context does not carry, so ``progress`` and
        ``cancellation`` keep working. Dunders raise ``AttributeError`` so
        copying, pickling and ``repr`` still behave like a plain object.
        """
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        reason = self._REFUSED.get(name)
        if reason is None:
            reason = (
                "a job body runs on a worker and only progress and cancellation "
                "are available there"
            )
        raise QgisSdkUnsupportedCapabilityError(name, reason)

    def __repr__(self) -> str:
        return "WorkerContext(progress=..., cancellation=...)"


@dataclass(frozen=True, slots=True)
class JobServices:
    """What one job attempt may be handed beyond its progress and scope.

    A job can reach a worker pool, the network, Processing and its owner's
    project; a host that has none of them leaves them ``None`` so reading the
    capability fails by name instead of silently doing nothing (decision-39).
    """

    workers: Workers | None = None
    network: Network | None = None
    algorithms: Algorithms | None = None
    project: Project | None = None


class JobContext(Context):
    """One job attempt, owned by a view unless plugin ownership is explicit.

    Built fresh for every attempt by :class:`qgis_sdk.jobs.JobService` and
    passed to the ``@job`` function as its first argument (decision-38); the
    function never builds one itself, and a test hands it a fake. The scope
    is the attempt's own: it closes when the attempt settles or the plugin
    unloads, not when the owning view is disposed, because closing it under a
    worker that has not acknowledged cancellation would be exactly the
    teardown decision-21 forbids. ``workers``, ``network``, ``algorithms`` and
    ``project`` are capabilities: ``await ctx.workers.offload(work)`` on a host
    without a pool fails by name, and so does ``invoke(buffer, ctx, ...)`` on
    a host without Processing (decision-42).
    """

    __slots__ = (
        "_algorithms",
        "_network",
        "_project",
        "_workers",
        "cancellation",
        "progress",
        "scope",
    )

    _capability_names = ("workers", "network", "algorithms", "project")

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    workers: Capability[Workers] = Capability()
    network: Capability[Network] = Capability()
    algorithms: Capability[Algorithms] = Capability()
    project: Capability[Project] = Capability()

    def __init__(
        self,
        progress: Progress,
        cancellation: Cancellation,
        scope: ResourceScope,
        services: JobServices | None = None,
    ) -> None:
        services = services if services is not None else JobServices()
        self._assemble(
            progress=progress,
            cancellation=cancellation,
            scope=scope,
            **{f"_{name}": getattr(services, name) for name in self._capability_names},
        )
