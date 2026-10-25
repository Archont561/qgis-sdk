"""Owner-scoped cleanup for pure and native runtime resources."""

from __future__ import annotations

from collections.abc import Callable

from qgis_sdk.models import QgisSdkScopeClosedError


def _attempt_cleanup(cleanup: Callable[[], None], failures: list[Exception]) -> None:
    """Continue releasing siblings even when a cleanup fails."""
    try:
        cleanup()
    except Exception as error:  # noqa: BLE001 - collect all cleanup failures
        failures.append(error)


class ResourceScope:
    """A runtime-owned scope passed explicitly to a context."""

    def __init__(self) -> None:
        self._closed = False
        self._callbacks: list[Callable[[], None]] = []
        self._children: dict[ResourceScope, None] = {}
        self._parent: ResourceScope | None = None

    @property
    def closed(self) -> bool:
        """Whether the owner has disposed this scope."""
        return self._closed

    def ensure_open(self) -> None:
        """Reject work after this owner has been disposed."""
        if self._closed:
            raise QgisSdkScopeClosedError()

    def child(self) -> ResourceScope:
        """Create a child owned by this scope, for a view or execution."""
        self.ensure_open()
        child = ResourceScope()
        child._parent = self
        self._children[child] = None
        return child

    def on_close(self, cleanup: Callable[[], None]) -> None:
        """Register a cleanup action (last registered, first run)."""
        self.ensure_open()
        self._callbacks.append(cleanup)

    def close(self) -> None:
        """Close once; the owner, not an author handler, calls this."""
        if self._closed:
            return
        self._closed = True
        if self._parent is not None:
            self._parent._children.pop(self, None)
            self._parent = None
        failures: list[Exception] = []
        for child in reversed(tuple(self._children)):
            _attempt_cleanup(child.close, failures)
        while self._callbacks:
            _attempt_cleanup(self._callbacks.pop(), failures)
        if failures:
            raise ExceptionGroup("Scope cleanup failed", failures)
