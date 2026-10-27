"""Subscriptions: what a handle hands a listener and how it is disposed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
)

from qgis_sdk.core import ResourceScope
from qgis_sdk.jobs._authoring import JobEvent

if TYPE_CHECKING:
    from qgis_sdk.jobs._attempt import _Attempt


# -- subscriptions ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobFault:
    """A subscriber that raised; it was detached and the job carried on."""

    job_id: str
    event: JobEvent
    error: BaseException


class JobSubscription:
    """One disposable callback registration on a handle."""

    __slots__ = ("_active", "_attempt", "_callback", "_event", "_owner")

    def __init__(
        self,
        attempt: _Attempt,
        event: JobEvent,
        callback: Callable,
        owner: ResourceScope | None = None,
    ) -> None:
        self._attempt = attempt
        self._event = event
        self._callback = callback
        self._owner = owner
        self._active = True

    @property
    def event(self) -> JobEvent:
        """Which of the four events this subscription listens to."""
        return self._event

    @property
    def active(self) -> bool:
        """Whether the callback can still be invoked."""
        return self._active

    def dispose(self) -> bool:
        """Stop delivery; return whether this call was the one that stopped it."""
        if not self._active:
            return False
        self._active = False
        self._attempt._subscriptions[self._event].pop(self, None)
        if self._owner is not None:
            self._attempt.runtime.release_owner_hook(self._owner, self)
        return True
