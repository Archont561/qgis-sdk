"""Lifecycle ownership for one plain author class and its runtime scope."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType

from qgis_sdk.declarations import PluginDescription, describe_plugin
from qgis_sdk.models import QgisSdkError, QgisSdkScopeClosedError

from .contexts import PluginContext

PluginFactory = Callable[[PluginContext], object]
"""Construct a plugin instance from the context supplied by the runtime."""

_EMPTY_ACTIONS: Mapping[str, Callable[..., object]] = MappingProxyType({})


class QgisSdkPluginLifecycleError(QgisSdkError):
    """The runtime refused a start, unload or action binding."""

    code = "invalid_plugin_lifecycle"


class PluginRuntimeState(StrEnum):
    """Observable lifecycle state of one plugin runtime."""

    NEW = "new"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class PluginRuntime:
    """Construct and dispose one plain plugin class without rewriting it.

    The runtime never inspects a constructor signature: the default factory
    calls ``plugin_class(context)`` and an explicit factory can supply custom
    dependencies. Declarations are validated at construction time, but no
    author code runs until :meth:`start`.
    """

    def __init__(
        self,
        plugin_class: type,
        context: PluginContext,
        *,
        instance_factory: PluginFactory | None = None,
    ) -> None:
        self._plugin_class = plugin_class
        self._context = context
        self._instance_factory = instance_factory
        self._description = describe_plugin(plugin_class)
        if context.scope.closed:
            raise QgisSdkScopeClosedError()
        self._state = PluginRuntimeState.NEW
        self._instance: object | None = None
        self._actions: Mapping[str, Callable[..., object]] = _EMPTY_ACTIONS

    @property
    def state(self) -> PluginRuntimeState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def description(self) -> PluginDescription:
        """Return the validated declaration of the wrapped plugin class."""
        return self._description

    @property
    def instance(self) -> object | None:
        """Return the constructed instance while running, else ``None``."""
        return self._instance

    @property
    def actions(self) -> Mapping[str, Callable[..., object]]:
        """Return declared handlers bound to the instance, keyed by action ID."""
        return self._actions

    def start(self) -> object:
        """Construct and bind the plugin once, or raise a typed lifecycle error."""
        if self._state is not PluginRuntimeState.NEW:
            raise QgisSdkPluginLifecycleError(
                f"Plugin {self._description.id!r} cannot start from state "
                f"{self._state.value!r}; expected 'new'"
            )
        if self._context.scope.closed:
            raise QgisSdkScopeClosedError()
        try:
            instance = self._construct()
            if not isinstance(instance, self._plugin_class):
                raise QgisSdkPluginLifecycleError(
                    f"Plugin {self._description.id!r}: the instance factory returned "
                    f"{type(instance).__name__}, not {self._plugin_class.__name__}"
                )
            actions = self._bind_actions(instance)
        except BaseException as error:
            cleanup_error = self._discard_after_failed_start()
            if cleanup_error is not None:
                raise error from cleanup_error
            raise
        self._instance = instance
        self._actions = MappingProxyType(actions)
        self._state = PluginRuntimeState.RUNNING
        return instance

    def unload(self) -> None:
        """Dispose owned resources once; later calls are safe no-ops.

        A failed startup is already disposed, so unloading it is also a no-op.
        Cleanup failures are raised after the runtime reaches ``stopped`` and
        all remaining callbacks have run.
        """
        if self._state in (PluginRuntimeState.STOPPED, PluginRuntimeState.FAILED):
            return
        self._state = PluginRuntimeState.STOPPED
        self._instance = None
        self._actions = _EMPTY_ACTIONS
        self._context.scope.close()

    def _construct(self) -> object:
        factory = self._instance_factory
        if factory is None:
            return self._plugin_class(self._context)
        return factory(self._context)

    def _bind_actions(self, instance: object) -> dict[str, Callable[..., object]]:
        bound: dict[str, Callable[..., object]] = {}
        for description in self._description.actions:
            handler = getattr(instance, description.handler, None)
            if not callable(handler):
                raise QgisSdkPluginLifecycleError(
                    f"Plugin {self._description.id!r}: action {description.id!r} "
                    f"handler {description.handler!r} is not callable on the "
                    "constructed instance"
                )
            bound[description.id] = handler
        return bound

    def _discard_after_failed_start(self) -> BaseException | None:
        self._state = PluginRuntimeState.FAILED
        self._instance = None
        self._actions = _EMPTY_ACTIONS
        try:
            self._context.scope.close()
        except BaseException as cleanup_error:  # noqa: BLE001 - preserve cleanup evidence
            return cleanup_error
        return None
