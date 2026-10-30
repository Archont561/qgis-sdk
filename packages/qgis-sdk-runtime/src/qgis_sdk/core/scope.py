"""Owner-scoped cleanup for pure and native runtime resources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qgis_sdk.models import QgisSdkScopeClosedError


def _attempt_cleanup(cleanup: Callable[[], None], failures: list[Exception]) -> None:
    """Continue releasing siblings even when a cleanup fails."""
    try:
        cleanup()
    except Exception as error:  # noqa: BLE001 - collect all cleanup failures
        failures.append(error)


@dataclass(frozen=True, slots=True)
class QuiesceOutcome:
    """Whether an owner reached a safe point for an in-process replacement."""

    refused: bool
    blockers: tuple[str, ...]

    @property
    def safe_to_replace(self) -> bool:
        """Return whether the host may dispose this generation now."""
        return not self.refused

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable summary for qualification reports."""
        return {"refused": self.refused, "blockers": list(self.blockers)}


_SCOPE_CLOSED_BLOCKER = "the scope is already closed"


class ResourceScope:
    """A runtime-owned scope passed explicitly to a context.

    Besides cleanup, a scope collects the *quiesce checks* of the owners that
    hold work in it (decision-15/21): a development host asks the plugin
    scope whether everything owned has reached a safe replacement point
    before it disposes anything, and a refusal names what is still running.
    """

    def __init__(self) -> None:
        self._closed = False
        self._callbacks: list[Callable[[], None]] = []
        self._children: dict[ResourceScope, None] = {}
        self._parent: ResourceScope | None = None
        self._quiescers: list[
            tuple[Callable[[], QuiesceOutcome], Callable[[], None] | None]
        ] = []

    @property
    def closed(self) -> bool:
        """Whether the owner has disposed this scope."""
        return self._closed

    @property
    def parent(self) -> ResourceScope | None:
        """The scope that owns this one, or ``None`` for a root scope.

        Ownership reads it to answer "is this caller one of ours?" - a view's
        scope descends from the plugin's - and it lets go when this scope
        closes, so a retained child never keeps its parent alive.
        """
        return self._parent

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

    def on_quiesce(
        self,
        check: Callable[[], QuiesceOutcome],
        *,
        resume: Callable[[], None] | None = None,
    ) -> None:
        """Register an owner's safe-point check, and how to accept work again."""
        self.ensure_open()
        self._quiescers.append((check, resume))

    def quiesce(self) -> QuiesceOutcome:
        """Ask every owner in this scope and its children for a safe point.

        Children answer first (a view's work before the plugin's). The result
        is refused when any owner refused, with every blocker named, so the
        host can report all of them at once rather than one per attempt.
        """
        if self._closed:
            return QuiesceOutcome(refused=True, blockers=(_SCOPE_CLOSED_BLOCKER,))
        blockers: list[str] = []
        for child in tuple(self._children):
            blockers.extend(child.quiesce().blockers)
        for check, _resume in tuple(self._quiescers):
            blockers.extend(check().blockers)
        return QuiesceOutcome(refused=bool(blockers), blockers=tuple(blockers))

    def resume(self) -> None:
        """Accept new work again everywhere after a refused replacement."""
        for child in tuple(self._children):
            child.resume()
        for _check, resume in tuple(self._quiescers):
            if resume is not None:
                resume()

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
        self._quiescers.clear()
        if failures:
            raise ExceptionGroup("Scope cleanup failed", failures)
