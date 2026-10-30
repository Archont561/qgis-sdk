"""Lifecycle ownership for one application and its runtime scope."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from qgis_sdk.declarations import PluginDescription, QgisSdkDeclarationError
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.models import QgisSdkError, QgisSdkScopeClosedError
from qgis_sdk.services import ProviderRegistration

from .contexts import PluginContext
from .scope import QuiesceOutcome

if TYPE_CHECKING:
    from qgis_sdk.core._application import QgisSdkPlugin
    from qgis_sdk.jobs import JobRegistry, JobService
    from qgis_sdk.providers import Provider

_PluginFactory = Callable[[PluginContext], object]
"""Internal factory for a lowered plugin instance."""

_CONTEXT_ATTRIBUTE = "ctx"
"""Context slot on each private lowered runtime class."""

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
    """Own one :class:`QgisSdkPlugin` and its context for a lifecycle.

    The runtime creates a private lowered instance for each application runtime,
    validates declarations and providers at construction, and injects the given
    context into registered functions. :meth:`start` registers providers when
    Processing is available; :meth:`unload` releases them and owned resources.
    A failed start rolls back its registrations.
    """

    def __init__(
        self,
        app: QgisSdkPlugin,
        context: PluginContext,
    ) -> None:
        from qgis_sdk.core._application import QgisSdkPlugin

        if not isinstance(app, QgisSdkPlugin):
            raise QgisSdkDeclarationError("PluginRuntime requires a QgisSdkPlugin")
        self._initialize(app._plugin_class(), context)

    @classmethod
    def _from_plugin_class(
        cls,
        plugin_class: type,
        context: PluginContext,
        *,
        instance_factory: _PluginFactory | None = None,
    ) -> PluginRuntime:
        """Internal entry point for already lowered classes."""
        runtime = cls.__new__(cls)
        runtime._initialize(plugin_class, context, instance_factory=instance_factory)
        return runtime

    def _initialize(
        self,
        plugin_class: type,
        context: PluginContext,
        *,
        instance_factory: _PluginFactory | None = None,
    ) -> None:
        self._plugin_class = plugin_class
        self._context = context
        self._instance_factory = instance_factory
        self._description = describe_plugin(plugin_class)
        self._providers = _declared_providers(plugin_class)
        # The registry is validated here, when the runtime is built, so a bad
        # name or an undeclared function is refused at startup rather than on
        # the first submission (TASK-116, decision-65 §2).
        self._registry = _job_registry(plugin_class, self._description.id)
        if context.scope.closed:
            raise QgisSdkScopeClosedError()
        self._jobs: JobService | None = None
        self._context = self._attach_jobs(context)
        self._state = PluginRuntimeState.NEW
        self._instance: object | None = None
        self._actions: Mapping[str, Callable[..., object]] = _EMPTY_ACTIONS
        self._streams: Mapping[str, Callable[..., object]] = _EMPTY_ACTIONS
        self._registrations: tuple[ProviderRegistration, ...] = ()

    @property
    def state(self) -> PluginRuntimeState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def description(self) -> PluginDescription:
        """Return the validated declaration of the wrapped plugin class."""
        return self._description

    @property
    def context(self) -> PluginContext:
        """Return the context this runtime binds to the plugin.

        The runtime adds ``jobs`` to the context it was given, when the plugin
        declares any, so a host reads the context back from here instead of
        keeping the one it built.
        """
        return self._context

    @property
    def jobs(self) -> JobService | None:
        """The plugin's job service, or ``None`` when it declares no jobs.

        Hosts drive it: :meth:`JobService.tick` on the GUI thread delivers
        progress and outcomes, and the plugin scope's quiesce asks it whether
        a replacement is safe. Authors reach the same jobs by name through
        ``ctx.jobs``.
        """
        return self._jobs

    @property
    def job_registry(self) -> JobRegistry:
        """The names the plugin declared, empty when it declares none."""
        return self._registry

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

    @property
    def providers(self) -> tuple[Provider, ...]:
        """Return the providers the class lists, whether or not a host shows them."""
        return self._providers

    @property
    def registered_providers(self) -> tuple[str, ...]:
        """Return the ids of the providers the host currently advertises.

        Empty over a context without ``processing``, before ``start()`` and
        after ``unload()``; registration is all-or-nothing, so while running
        it is either every listed provider or none.
        """
        if not self._registrations:
            return ()
        return tuple(provider.id for provider in self._providers)

    @property
    def algorithms(self) -> tuple[str, ...]:
        """Return the Processing algorithm ids this runtime registered.

        ``provider:algorithm`` - the id ``processing.run`` and the toolbox take -
        for every algorithm of every provider the host currently advertises. It
        is empty over a context without ``processing``, before ``start()`` and
        after ``unload()``, the same moments :attr:`registered_providers` is
        empty; a console reads it to know what a running plugin added to QGIS.
        """
        if not self._registrations:
            return ()
        return tuple(
            f"{provider.id}:{described.id}"
            for provider in self._providers
            for described in provider.describe().algorithms
        )

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
            self._register_providers()
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

    def quiesce(self) -> QuiesceOutcome:
        """Ask everything the plugin owns for a safe replacement point.

        For a development host about to unload this revision (decision-15):
        refused means work is still running and the revision must be left as
        it is - ``resume()`` lets it accept work again. A plugin that is not
        running has nothing to quiesce and refuses, naming its state.
        """
        if self._state is not PluginRuntimeState.RUNNING:
            return QuiesceOutcome(
                refused=True,
                blockers=(f"the plugin is not running (state {self._state.value})",),
            )
        return self._context.scope.quiesce()

    def resume(self) -> None:
        """Accept work again after a refused replacement."""
        if self._state is PluginRuntimeState.RUNNING:
            self._context.scope.resume()

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
        try:
            self._unregister_providers()
        finally:
            self._context.scope.close()

    def _attach_jobs(self, context: PluginContext) -> PluginContext:
        """Give ``context`` its ``jobs`` capability, built from the registry.

        A plugin that declares no jobs keeps whatever its host provided (a
        host may supply one), and one that declares them gets a service over
        its own scope with the host's worker backend. A host that provides
        ``jobs`` *and* a plugin that declares them is refused: two registries
        for one plugin would mean two answers to ``ctx.jobs.add``.
        """
        if len(self._registry) == 0:
            return context
        if context.has("jobs"):
            raise QgisSdkDeclarationError(
                f"Plugin {self._description.id!r}: the host already provides "
                "'jobs' and the plugin declares its own registry; keep one"
            )
        from qgis_sdk.jobs import Jobs, JobService

        service = JobService(
            context.scope,
            workers=context.workers if context.has("workers") else None,
            registry=self._registry,
        )
        self._jobs = service
        return context.with_services(jobs=Jobs(service))

    def _register_providers(self) -> None:
        """Advertise the listed providers through ``ctx.processing``, if any.

        Registration is all-or-nothing: a host that refuses one provider (an
        id another plugin already holds) gets the ones before it removed again
        before the refusal propagates, so a failed start advertises nothing.
        """
        if not self._providers or not self._context.has("processing"):
            return
        processing = self._context.processing
        registered: list[ProviderRegistration] = []
        try:
            for provider in self._providers:
                registered.append(processing.register_provider(provider))
        except BaseException:
            self._registrations = tuple(registered)
            self._unregister_providers()
            raise
        self._registrations = tuple(registered)

    def _unregister_providers(self) -> None:
        """Remove every registration this runtime made, last first."""
        registrations, self._registrations = self._registrations, ()
        for registration in reversed(registrations):
            registration.unregister()

    def _bind_context(self) -> None:
        """Make ``plugin_class.ctx`` this runtime's context.

        The most recently started runtime owns the attribute: a class is meant
        to run under one runtime at a time, and rebinding rather than refusing
        means a runtime that was never unloaded cannot poison the class.
        """
        setattr(self._plugin_class, _CONTEXT_ATTRIBUTE, self._context)

    def _unbind_context(self) -> None:
        """Remove ``plugin_class.ctx`` again, but only if it is still ours."""
        if vars(self._plugin_class).get(_CONTEXT_ATTRIBUTE) is self._context:
            delattr(self._plugin_class, _CONTEXT_ATTRIBUTE)

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
                f"arguments; read the context from the {_CONTEXT_ATTRIBUTE!r} class "
                f"attribute (annotate `{_CONTEXT_ATTRIBUTE}: PluginContext`) instead "
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
            self._unregister_providers()
            self._context.scope.close()
        except BaseException as cleanup_error:  # noqa: BLE001 - preserve cleanup evidence
            return cleanup_error
        return None


def _declared_providers(plugin_class: type) -> tuple[Provider, ...]:
    """Validate ``providers = [...]`` without importing the providers module eagerly.

    ``qgis_sdk.providers`` imports this package, so the lookup is deferred to
    construction time; the module is pure and always importable.
    """
    from qgis_sdk.providers import _declared_providers as validate_providers

    return validate_providers(plugin_class)


def _job_registry(plugin_class: type, plugin_id: str) -> JobRegistry:
    """The plugin's ``jobs = ...`` declaration, validated (TASK-116).

    Read from the class the plugin actually runs - an intermediate author base
    counts too - and never from a module scan: what a plugin exposes is what it
    wrote down.
    """
    from qgis_sdk.jobs import JobRegistry

    for base in plugin_class.__mro__:
        if "jobs" in vars(base):
            return JobRegistry.from_declaration(
                vars(base)["jobs"], path=f"Plugin {plugin_id!r}"
            )
    return JobRegistry.empty(f"Plugin {plugin_id!r}")
