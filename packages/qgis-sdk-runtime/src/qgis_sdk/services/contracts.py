"""Small host-facing Protocols for the first pure authoring slice."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, TypeVar

from .notifications import Notifications

__all__ = [
    "Cancellation",
    "DesktopAccess",
    "Notifications",
    "ObservableProgress",
    "Progress",
    "Ui",
    "ViewControl",
    "WorkItem",
    "Workers",
]

T_co = TypeVar("T_co", covariant=True)


class Cancellation(Protocol):
    """Read-only cancellation signal for one execution, not plugin state."""

    def is_cancelled(self) -> bool: ...


class Progress(Protocol):
    """Report a fraction from 0.0 to 1.0 for one execution."""

    def report(self, fraction: float) -> None: ...


class ObservableProgress(Progress, Protocol):
    """A ``Progress`` a backend can mirror into a surface it owns.

    The job runtime's progress is observable, so a backend that shows work to a
    user - the QGIS task manager's task bar - can follow every report without
    the author knowing: the callback runs on the thread that reported, and the
    backend is responsible for marshalling anything it touches.
    """

    def observe(self, callback: Callable[[float], None]) -> None:
        """Hear each fraction reported from now on, on the reporting thread."""
        ...


@dataclass(frozen=True, slots=True)
class WorkItem:
    """What a backend may show and honour while it runs one job body (decision-65).

    ``offload`` receives one when the work is a declared job, so a backend that
    presents work to a user can title it and follow it. ``progress`` is the
    attempt's observable progress (a backend may mirror it into its own bar),
    and ``cancel`` asks the job to stop - it is what a task bar's cancel button
    calls, and it is a request, never an interruption (decision-21).
    """

    title: str
    progress: Progress | None = None
    cancel: Callable[[], None] | None = None


class ViewControl(Protocol):
    """Request view closure; the owning runtime decides when to dispose it."""

    def request_close(self) -> None: ...


class Ui(Protocol):
    """Open one of the plugin's registered surfaces (decision-55).

    ``surface`` is a ``Dialog``/``Dock`` subclass listed in the plugin's
    ``surfaces = [...]``; ``initial`` is handed to the instance as
    ``self.initial`` before ``build()``. The Desktop host shows the window
    and returns the surface instance; the fake records the request; a host
    without a GUI does not provide the capability at all.
    """

    def open(
        self, surface: type, *, initial: Mapping[str, object] | None = None
    ) -> object: ...


class DesktopAccess(Protocol):
    """Explicit native Desktop escape hatch; never a serializable bridge value."""

    @property
    def iface(self) -> object:
        """The runtime-owned QGIS Desktop interface (opaque to pure code)."""
        ...


class Workers(Protocol):
    """Run one plain callable off the thread that drives the scheduler.

    ``offload`` returns an awaitable the job suspends on; the callable runs on
    a worker the host owns (``QgsTaskManager`` in QGIS Desktop, a scripted fake
    in a test) and its return value or exception resumes the job on the driving
    thread at the next tick. The callable must be worker-safe: no widgets, no
    live layers - it may poll the job's ``Cancellation`` and report
    ``Progress``, both of which are thread-safe by contract.

    ``item`` describes the work when it is a declared job: its title, its
    progress and how to request its cancellation. A backend that shows work to
    a user uses it; one that does not ignores it, and ``offload(fn)`` alone
    stays valid.
    """

    def offload(
        self, fn: Callable[[], T_co], *, item: WorkItem | None = None
    ) -> Awaitable[T_co]: ...
