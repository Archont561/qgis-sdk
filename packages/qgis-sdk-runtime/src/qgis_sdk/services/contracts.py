"""Small host-facing Protocols for the first pure authoring slice."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class Notifications(Protocol):
    """Publish an informational message through the chosen runtime."""

    def info(self, message: str) -> None: ...


class Cancellation(Protocol):
    """Read-only cancellation signal for one execution, not plugin state."""

    def is_cancelled(self) -> bool: ...


class Progress(Protocol):
    """Report a fraction from 0.0 to 1.0 for one execution."""

    def report(self, fraction: float) -> None: ...


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
    a worker the host owns (a ``QThreadPool`` in QGIS, a scripted fake in a
    test) and its return value or exception resumes the job on the driving
    thread at the next tick. The callable must be worker-safe: no widgets, no
    live layers - it may poll the job's ``Cancellation`` and report
    ``Progress``, both of which are thread-safe by contract.
    """

    def offload(self, fn: Callable[[], T_co]) -> Awaitable[T_co]: ...
