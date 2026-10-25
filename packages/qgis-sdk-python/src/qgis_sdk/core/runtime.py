"""Lifecycle ownership for one plain author class and its runtime scope."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType

from qgis_sdk.declarations import PluginDescription, describe_plugin
from qgis_sdk.models import QgisSdkError, QgisSdkScopeClosedError

from .contexts import PluginContext

PluginFactory = Callable[[PluginContext], object]
"""Construct a plugin instance from the context supplied by the runtime."""

CONTEXT_ATTRIBUTE = "ctx"
"""The class attribute a running runtime binds its :class:`PluginContext` to.

An author class annotates it (``ctx: PluginContext``) for the type checker and
reads ``self.ctx`` anywhere, including ``__init__``; the runtime sets it on the
class before construction and removes it again on unload, so the class is plain
outside a running lifecycle and never retains a closed scope.
"""

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

    The context is bound as the ``ctx`` class attribute (:data:`CONTEXT_ATTRIBUTE`)
    for the duration of the lifecycle, and the class is constructed with no
    arguments (decision-31). The default construction is ``plugin_class()``; an
    explicit factory still receives the context and can supply custom
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
        self._streams: Mapping[str, Callable[..., object]] = _EMPTY_ACTIONS

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

    @property
    def streams(self) -> Mapping[str, Callable[..., object]]:
        """Return declared stream factories bound to the instance, keyed by id."""
        return self._streams

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
            self._bind_context()
            instance = self._construct()
            if not isinstance(instance, self._plugin_class):
                raise QgisSdkPluginLifecycleError(
                    f"Plugin {self._description.id!r}: the instance factory returned "
                    f"{type(instance).__name__}, not {self._plugin_class.__name__}"
                )
            actions = self._bind(instance, self._description.actions, "action")
            streams = self._bind(instance, self._description.streams, "stream")
        except BaseException as error:
            cleanup_error = self._discard_after_failed_start()
            if cleanup_error is not None:
                raise error from cleanup_error
            raise
        self._instance = instance
        self._actions = MappingProxyType(actions)
        self._streams = MappingProxyType(streams)
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
        self._streams = _EMPTY_ACTIONS
        self._unbind_context()
        self._context.scope.close()

    def _bind_context(self) -> None:
        """Make ``plugin_class.ctx`` this runtime's context.

        The most recently started runtime owns the attribute: a class is meant
        to run under one runtime at a time, and rebinding rather than refusing
        means a runtime that was never unloaded cannot poison the class.
        """
        setattr(self._plugin_class, CONTEXT_ATTRIBUTE, self._context)

    def _unbind_context(self) -> None:
        """Remove ``plugin_class.ctx`` again, but only if it is still ours."""
        if vars(self._plugin_class).get(CONTEXT_ATTRIBUTE) is self._context:
            delattr(self._plugin_class, CONTEXT_ATTRIBUTE)

    def _construct(self) -> object:
        factory = self._instance_factory
        if factory is not None:
            return factory(self._context)
        try:
            return self._plugin_class()
        except TypeError as error:
            if not self._constructor_requires_arguments():
                raise
            raise QgisSdkPluginLifecycleError(
                f"Plugin {self._description.id!r}: the class is constructed with no "
                f"arguments; read the context from the {CONTEXT_ATTRIBUTE!r} class "
                f"attribute (annotate `{CONTEXT_ATTRIBUTE}: PluginContext`) instead "
                "of a constructor parameter"
            ) from error

    def _constructor_requires_arguments(self) -> bool:
        """Only consulted to explain a failed ``plugin_class()``, never to adapt."""
        try:
            parameters = inspect.signature(self._plugin_class).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(
            parameter.default is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
            for parameter in parameters
        )

    def _bind(
        self, instance: object, declared: tuple, noun: str
    ) -> dict[str, Callable[..., object]]:
        bound: dict[str, Callable[..., object]] = {}
        for description in declared:
            handler = getattr(instance, description.handler, None)
            if not callable(handler):
                raise QgisSdkPluginLifecycleError(
                    f"Plugin {self._description.id!r}: {noun} {description.id!r} "
                    f"handler {description.handler!r} is not callable on the "
                    "constructed instance"
                )
            bound[description.id] = handler
        return bound

    def _discard_after_failed_start(self) -> BaseException | None:
        self._state = PluginRuntimeState.FAILED
        self._instance = None
        self._actions = _EMPTY_ACTIONS
        self._streams = _EMPTY_ACTIONS
        self._unbind_context()
        try:
            self._context.scope.close()
        except BaseException as cleanup_error:  # noqa: BLE001 - preserve cleanup evidence
            return cleanup_error
        return None
