"""The recording fakes: notifications, the log, and the Processing registry.

Each one answers a host-facing service by writing down what it was handed, so a
test asserts on the record rather than on a screenshot or a log file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.services import (
    LogBase,
    LogRecord,
    Notification,
    NotificationsBase,
)

if TYPE_CHECKING:
    from qgis_sdk.providers import Provider

__all__ = [
    "FakeProcessing",
    "FakeProviderRegistration",
    "RecordingLog",
    "RecordingNotifications",
]


class RecordingNotifications(NotificationsBase):
    """A ``Notifications`` backend that records what it was given.

    ``messages`` is every message text in order, whatever its level - the
    assertion most tests want; ``records`` keeps the level and the button
    ``with_action`` attached, so a test can press it with :meth:`press`.
    """

    def __init__(self, scope: ResourceScope) -> None:
        """Build the recorder over one scope.

        Args:
            scope: The resource scope the fake belongs to.
        """
        self._scope = scope
        self.messages: list[str] = []
        self.records: list[Notification] = []
        self._dispatch: list[Callable[..., object] | None] = [None]

    def bind_actions(self, dispatch: Callable[..., object]) -> None:
        """Make :meth:`press` run ``dispatch(action_id, **arguments)``.

        Args:
            dispatch: What pressing a button runs.
        """
        self._dispatch[0] = dispatch

    def press(self, index: int = -1) -> object:
        """Press the button of the ``index``-th record, as the user would.

        Args:
            index: Which record's button to press, counting from zero.
        """
        record = self.records[index]
        if record.action is None:
            raise ValueError(f"notification {record.message!r} carries no action")
        dispatch = self._dispatch[0]
        if dispatch is None:
            raise ValueError(
                "no actions bound: call bind_actions(runtime.actions...) first"
            )
        return dispatch(record.action.action_id, **record.action.arguments)

    def _deliver(self, notification: Notification) -> None:
        self._scope.ensure_open()
        self.messages.append(notification.message)
        self.records.append(notification)


class RecordingLog(LogBase):
    """A ``Log`` backend that keeps every record it was given.

    ``records`` is the full :class:`LogRecord` list in order; ``messages``
    the message texts alone, whatever their level. ``plugin`` is the tag
    the records carry, ``"test"`` unless a test names its plugin.
    """

    def __init__(self, scope: ResourceScope, plugin: str = "test") -> None:
        """Build the log recorder over one scope.

        Args:
            scope: The resource scope the fake belongs to.
            plugin: The plugin id the records carry.
        """
        super().__init__(plugin)
        self._scope = scope
        self.records: list[LogRecord] = []

    @property
    def messages(self) -> list[str]:
        """The message text of every record, in order."""
        return [record.message for record in self.records]

    def _deliver(self, record: LogRecord) -> None:
        self._scope.ensure_open()
        self.records.append(record)


class FakeProviderRegistration:
    """One provider a :class:`FakeProcessing` currently advertises."""

    def __init__(self, registry: FakeProcessing, provider: Provider) -> None:
        self._registry = registry
        self.provider = provider

    def unregister(self) -> None:
        """Take the provider down; a second call is a safe no-op."""
        self._registry._remove(self.provider.id, self)


class FakeProcessing:
    """A ``Processing`` registry that records what a host would advertise.

    It holds no toolbox, so it proves only the contract ``PluginRuntime``
    relies on: ``register_provider`` records the provider under its id,
    refuses a second registration of the same id by name - the way the QGIS
    registry refuses a duplicate provider - and ``unregister`` on the returned
    registration removes it again. ``registered`` is the ids currently held,
    in registration order; ``events`` is the full history a test can assert
    ordering against.
    """

    def __init__(self, scope: ResourceScope) -> None:
        """Build the registry over one scope.

        Args:
            scope: The resource scope the fake belongs to.
        """
        self._scope = scope
        self._live: dict[str, FakeProviderRegistration] = {}
        self.events: list[tuple[str, str]] = []

    @property
    def registered(self) -> tuple[str, ...]:
        """The ids of the providers currently advertised."""
        return tuple(self._live)

    def provider(self, provider_id: str) -> Provider:
        """Return the provider advertised under ``provider_id``.

        Args:
            provider_id: The id the provider was advertised under.
        """
        return self._live[provider_id].provider

    def register_provider(self, provider: Provider) -> FakeProviderRegistration:
        """Advertise ``provider``, refusing an id that is already live.

        Args:
            provider: The provider to advertise.
        """
        self._scope.ensure_open()
        if provider.id in self._live:
            raise QgisSdkDeclarationError(
                f"provider {provider.id!r} is already registered with the host"
            )
        registration = FakeProviderRegistration(self, provider)
        self._live[provider.id] = registration
        self.events.append(("register", provider.id))
        return registration

    def _remove(self, provider_id: str, registration: FakeProviderRegistration) -> None:
        if self._live.get(provider_id) is registration:
            del self._live[provider_id]
            self.events.append(("unregister", provider_id))
