"""What releasing a handle means, per kind of handle.

A web view holds three very different things, and they must not share a disposal
path (AC #7):

* a **borrowed** layer is the project's. Releasing it drops the view's claim;
  nothing is deleted, ever, because the layer was never the view's to delete.
* an **owned** temporary output is the view's. Releasing it deletes the file the
  workflow produced, exactly once.
* a **subscription** is a stream. Releasing it disposes the subscription, and a
  subscription that already ended is not an error - a closing UI races with the
  terminal frame all the time.

Two properties are the point of the ledger: releasing twice is not releasing
twice, and releasing a borrowed handle cannot reach the layer.

The ledger is deliberately plain Python. It holds no Qt object and no QGIS
layer; it holds ids and the callbacks a host gave it, so the rules can be tested
without either.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError


class HandleKind(str, Enum):
    """The three things a view can hold a reference to."""

    BORROWED = "borrowed"
    OWNED = "owned"
    SUBSCRIPTION = "subscription"


class ReleaseOutcome(str, Enum):
    """What a release actually did, as the view is told."""

    BORROWED_RETAINED = "borrowed_retained"
    DELETED = "deleted"
    SUBSCRIPTION_DISPOSED = "subscription_disposed"
    ALREADY_RELEASED = "already_released"


@dataclass(frozen=True, slots=True)
class Handle:
    """One reference a view holds, named by kind and id."""

    kind: HandleKind
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, HandleKind):
            raise QgisSdkBridgeError(f"{self.kind!r} is not a handle kind")
        if not isinstance(self.id, str) or not self.id.strip():
            raise QgisSdkBridgeError("a handle id must be a nonempty string")

    @classmethod
    def parse(cls, raw: Any) -> Handle:
        """Read a handle from wire data, refusing anything else."""
        if not isinstance(raw, dict):
            raise QgisSdkBridgeError("a handle must be an object")
        unknown = set(raw) - {"kind", "id"}
        if unknown:
            raise QgisSdkBridgeError(
                f"unknown handle field(s): {', '.join(sorted(unknown))}"
            )
        try:
            kind = HandleKind(raw.get("kind"))
        except ValueError as error:
            raise QgisSdkBridgeError(
                f"unknown handle kind {raw.get('kind')!r}"
            ) from error
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise QgisSdkBridgeError("a handle id must be a nonempty string")
        return cls(kind=kind, id=identifier)

    def to_dict(self) -> dict[str, str]:
        """Return the wire shape of this handle."""
        return {"kind": self.kind.value, "id": self.id}


def _no_owned(handle_id: str) -> None:
    """The default: a host with no temporary outputs deletes nothing."""


def _no_subscription(subscription_id: str) -> bool:
    """The default: a host with no subscription registry disposes nothing."""
    return False


@dataclass(slots=True)
class ReleaseLedger:
    """Track one view's handles and release them according to their kind."""

    delete_owned: Callable[[str], None] = _no_owned
    dispose_subscription: Callable[[str], bool] = _no_subscription
    _held: dict[str, set[Handle]] = field(default_factory=dict, repr=False)

    def track(self, view_id: str, handle: Handle) -> None:
        """Record that ``view_id`` holds ``handle``."""
        self._held.setdefault(view_id, set()).add(handle)

    def forget(self, view_id: str, handle: Handle) -> None:
        """Drop the record without releasing anything (a normal unsubscribe)."""
        held = self._held.get(view_id)
        if held is not None:
            held.discard(handle)

    def holds(self, view_id: str, handle: Handle) -> bool:
        """Whether ``view_id`` still holds ``handle``."""
        return handle in self._held.get(view_id, set())

    def handles(self, view_id: str) -> tuple[Handle, ...]:
        """Every handle the view holds, in a stable order."""
        return tuple(
            sorted(self._held.get(view_id, set()), key=lambda item: (item.kind.value, item.id))
        )

    def release(self, view_id: str, handle: Handle) -> ReleaseOutcome:
        """Release one handle, once.

        A handle the view does not hold any more is ``already_released``
        whatever its kind: a second release must not delete a file twice, and it
        must not turn a closing view into a failed call.
        """
        if not self.holds(view_id, handle):
            return ReleaseOutcome.ALREADY_RELEASED
        self.forget(view_id, handle)
        if handle.kind is HandleKind.BORROWED:
            # Nothing to undo: the layer belongs to the project, and the only
            # thing the view ever had was a reference.
            return ReleaseOutcome.BORROWED_RETAINED
        if handle.kind is HandleKind.OWNED:
            self.delete_owned(handle.id)
            return ReleaseOutcome.DELETED
        disposed = self.dispose_subscription(handle.id)
        return (
            ReleaseOutcome.SUBSCRIPTION_DISPOSED
            if disposed
            else ReleaseOutcome.ALREADY_RELEASED
        )

    def release_view(self, view_id: str) -> list[dict[str, str]]:
        """Release everything a view holds, for a view that is going away."""
        results: list[dict[str, str]] = []
        for handle in self.handles(view_id):
            outcome = self.release(view_id, handle)
            results.append(
                {"kind": handle.kind.value, "id": handle.id, "outcome": outcome.value}
            )
        return results

    def release_all(self, view_id: str, handles: Iterable[Handle]) -> list[dict[str, str]]:
        """Release a named list of handles, reporting each outcome."""
        return [
            {
                "kind": handle.kind.value,
                "id": handle.id,
                "outcome": self.release(view_id, handle).value,
            }
            for handle in handles
        ]


__all__ = [
    "Handle",
    "HandleKind",
    "ReleaseLedger",
    "ReleaseOutcome",
]
