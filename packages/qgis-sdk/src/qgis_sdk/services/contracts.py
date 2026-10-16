"""Small host-facing Protocols for the first pure authoring slice."""

from typing import Protocol


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


class DesktopAccess(Protocol):
    """Explicit native Desktop escape hatch; never a serializable bridge value."""

    @property
    def iface(self) -> object:
        """The runtime-owned QGIS Desktop interface (opaque to pure code)."""
        ...
