"""Notification levels and ``with_action`` (decision-55 point 3).

``ctx.notifications`` speaks four levels - ``info``, ``success``, ``warning``,
``critical`` - and ``with_action(label, action_id, **arguments)`` returns the
same service with one button attached: pressing it runs one of the plugin's
declared actions. Where a message lands is the host's business (the QGIS
message bar on the Desktop, the message log headless, a list under the
fakes); every backend subclasses :class:`NotificationsBase` and implements
``_deliver`` once.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol

NotificationLevel = Literal["info", "success", "warning", "critical"]

LEVELS: tuple[NotificationLevel, ...] = ("info", "success", "warning", "critical")

__all__ = [
    "LEVELS",
    "Notification",
    "NotificationAction",
    "NotificationLevel",
    "Notifications",
    "NotificationsBase",
]


@dataclass(frozen=True, slots=True)
class NotificationAction:
    """The button a notification carries: its label and the action it runs."""

    label: str
    action_id: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Notification:
    """One delivered message, as a backend sees it."""

    level: NotificationLevel
    message: str
    action: NotificationAction | None = None


class Notifications(Protocol):
    """Publish a message through the chosen runtime, at one of four levels."""

    def info(self, message: str) -> None: ...

    def success(self, message: str) -> None: ...

    def warning(self, message: str) -> None: ...

    def critical(self, message: str) -> None: ...

    def with_action(
        self, label: str, action_id: str, /, **arguments: Any
    ) -> Notifications:
        """The same service, with a button that runs ``action_id`` attached."""
        ...


class NotificationsBase:
    """The four levels and ``with_action`` over one ``_deliver(notification)``."""

    _action: NotificationAction | None = None

    def info(self, message: str) -> None:
        self._deliver(Notification("info", message, self._action))

    def success(self, message: str) -> None:
        self._deliver(Notification("success", message, self._action))

    def warning(self, message: str) -> None:
        self._deliver(Notification("warning", message, self._action))

    def critical(self, message: str) -> None:
        self._deliver(Notification("critical", message, self._action))

    def with_action(self, label: str, action_id: str, /, **arguments: Any) -> Any:
        """A shallow copy of this service carrying the button; the sink is shared."""
        if not label or not action_id:
            raise ValueError("with_action needs a label and an action id")
        clone = copy.copy(self)
        clone._action = NotificationAction(
            label, action_id, MappingProxyType(dict(arguments))
        )
        return clone

    def _deliver(self, notification: Notification) -> None:
        raise NotImplementedError
