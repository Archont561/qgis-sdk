"""Explicit plugin declarations and composition."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from qgis_sdk.core.contexts import PluginContext
from qgis_sdk.declarations import (
    BINDING_ORDER_ATTRIBUTE,
    BINDINGS_ATTRIBUTE,
    WIRES_ATTRIBUTE,
    QgisSdkDeclarationError,
    attach_describe,
    derive_title,
    register_describer,
    register_predicate_describer,
    resolve_hints,
    validate_given,
)
from qgis_sdk.declarations._describe import _describe_lowered_plugin
from qgis_sdk.declarations._plugin import action, plugin, stream

if TYPE_CHECKING:
    from qgis_sdk.declarations import PluginDescription
    from qgis_sdk.providers import Provider
    from qgis_sdk.ui.surfaces import Surface

F = TypeVar("F", bound=Callable[..., Any])
S = TypeVar("S", bound="Surface")
_Entry = tuple[str, str, Callable[..., Any], dict[str, Any] | None]


def _validate_metadata(id: str, title: str) -> None:
    if not isinstance(id, str) or not isinstance(title, str):
        raise QgisSdkDeclarationError("id and title must be strings")
    validate_given(id, title)


def _lower_handler(function: Callable[..., Any]) -> Callable[..., Any]:
    def invoke(self, /, *args, **kwargs):
        return function(self.ctx, *args, **kwargs)

    return invoke


def _lower_stream(function: Callable[..., Any]) -> Callable[..., Any]:
    def invoke(self, /, *args, **kwargs):
        yield from function(self.ctx, *args, **kwargs)

    return invoke


class _ActionRegistry:
    """A reusable, explicitly included collection of functions."""

    def __init__(self) -> None:
        self._actions: list[_Entry] = []

    def action(self, *, id: str, title: str) -> Callable[[F], F]:
        _validate_metadata(id, title)

        def register(function: F) -> F:
            self._register(id, title, function, None)
            return function

        return register

    def stream(
        self, *, id: str, title: str, events: Mapping[str, Any]
    ) -> Callable[[F], F]:
        _validate_metadata(id, title)

        def register(function: F) -> F:
            self._register(id, title, function, dict(events))
            return function

        return register

    def _register(
        self,
        id: str,
        title: str,
        function: Callable[..., Any],
        events: dict[str, Any] | None,
    ) -> None:
        if not inspect.isfunction(function):
            raise QgisSdkDeclarationError("registration requires a function")
        entry = (id, title, function, events)
        existing = vars(function).get("__qgis_sdk_app_action__")
        if existing is not None and existing != entry:
            raise QgisSdkDeclarationError(
                "duplicate function with different application metadata"
            )
        if any(
            marker in vars(function)
            for marker in ("__qgis_sdk_action__", "__qgis_sdk_stream__")
        ):
            raise QgisSdkDeclarationError(
                "function already has an SDK action or stream declaration"
            )
        before = self._actions
        self._extend([entry])
        try:
            attach_describe(function)
        except BaseException:
            self._actions = before
            raise
        function.__qgis_sdk_app_action__ = entry

    def _extend(self, candidates: list[_Entry]) -> None:
        combined = [*self._actions, *candidates]
        if any(not inspect.isfunction(entry[2]) for entry in combined):
            raise QgisSdkDeclarationError("registration requires a function")
        ids = [entry[0] for entry in combined]
        names = [entry[2].__name__ for entry in combined]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise QgisSdkDeclarationError("duplicate action id or handler name")
        self._actions = combined


class QgisSdkPlugin(_ActionRegistry):
    """Collect functions explicitly and lower them to an SDK plugin class."""

    def __init__(self, *, id: str | None = None, title: str | None = None) -> None:
        if id is None:
            try:
                module = sys._getframe(1).f_globals.get("__name__")
            except (AttributeError, ValueError):
                module = None
            if not isinstance(module, str) or module == "__main__":
                raise QgisSdkDeclarationError(
                    "cannot derive plugin id from the declaring module; pass id= explicitly"
                )
            id = module
        if title is None:
            if not isinstance(id, str):
                raise QgisSdkDeclarationError("id and title must be strings")
            parts = id.split(".")
            name = parts[-2] if len(parts) > 1 and parts[-1] == "plugin" else parts[-1]
            title = derive_title(name.replace("-", "_"))
        _validate_metadata(id, title)
        super().__init__()
        self.id = id
        self.title = title
        self._surfaces: list[type[Surface]] = []
        self._providers: list[Provider] = []
        self._jobs: Any = None
        self._declared_jobs: dict[str, Callable[..., Any]] = {}
        self._included_plugins: set[QgisSdkPlugin] = set()
        self._included_members: set[QgisSdkPlugin] = set()
        self.context_factory: Callable[[object | None], PluginContext] | None = None

    @property
    def surfaces(self) -> tuple[type[Surface], ...]:
        """The surfaces owned by this application."""
        return tuple(self._surfaces)

    @property
    def providers(self) -> tuple[Provider, ...]:
        """The Processing providers owned by this application."""
        return tuple(self._providers)

    @property
    def jobs(self) -> Any:
        """The named jobs an action reaches as ``ctx.jobs.<name>`` (TASK-116).

        ``None`` until the plugin declares some. Three spellings, one registry:
        a mapping (``app.jobs = {"add": add}``), a sequence of ``@job``
        functions (``app.jobs = (add, count_features)``), or the decorator
        (``@app.job()`` above the function). Each is validated at once, and the
        runtime builds the registry again from the result when the plugin
        starts.
        """
        if not self._declared_jobs:
            return self._jobs
        declared: dict[str, Callable[..., Any]] = {}
        if self._jobs is not None:
            from qgis_sdk.jobs import JobRegistry

            registry = JobRegistry.from_declaration(
                self._jobs, path=f"Plugin {self.id!r}"
            )
            declared = {name: registry.function(name) for name in registry.names}
        declared.update(self._declared_jobs)
        return declared

    @jobs.setter
    def jobs(self, declaration: Any) -> None:
        if declaration is not None:
            from qgis_sdk.jobs import JobRegistry

            registry = JobRegistry.from_declaration(
                declaration, path=f"Plugin {self.id!r}"
            )
            shared = sorted(set(registry.names) & set(self._declared_jobs))
            if shared:
                raise QgisSdkDeclarationError(
                    f"Plugin {self.id!r}: {shared[0]!r} is both assigned in `jobs` "
                    "and declared with @app.job; keep one declaration per name"
                )
        self._jobs = declaration

    def job(
        self,
        function: Callable[..., Any] | None = None,
        /,
        *,
        key: str | None = None,
        id: str | None = None,
        title: str | None = None,
    ) -> Any:
        """Declare one ``@job`` function as ``ctx.jobs.<name>``, decorator style.

        The shape an action already has::

            @app.job(id="demo.sum", title="Sum")
            def add(ctx: WorkerContext, left: int, right: int) -> SumResult: ...

            @app.job()          # id, title and name all derived from the function
            def count_features(ctx: WorkerContext, layer_id: str) -> int: ...

            @app.job(key="sum") # a name that differs from the function's own
            def add(ctx: WorkerContext, ...) -> ...: ...

        The name is the function's, snake_cased, exactly as a sequence entry of
        ``app.jobs`` derives it; ``key=`` renames it the way a mapping key does.
        The function keeps its ``@job`` metadata - applying it here when the
        author did not - so ``describe_job(add)`` works either way.
        """
        if function is None:
            return lambda target: self.job(target, key=key, id=id, title=title)
        if not inspect.isfunction(function):
            raise QgisSdkDeclarationError("@app.job declares a function")
        from qgis_sdk.declarations import derive_id
        from qgis_sdk.jobs import JobRegistry
        from qgis_sdk.jobs import job as declare_job

        if id is not None or title is not None:
            declare_job(id=id, title=title)(function)
        elif "__qgis_sdk_job__" not in vars(function):
            declare_job(function)
        name = key if key is not None else derive_id(function.__name__)
        if name in self._declared_jobs:
            raise QgisSdkDeclarationError(
                f"Plugin {self.id!r}: two jobs are named {name!r}; give one of "
                "them another name with @app.job(key=...)"
            )
        # One call validates the name, the decoration, the reserved names and a
        # second name for an id this plugin already declares.
        JobRegistry.from_declaration(
            {**self._declared_jobs, name: function}, path=f"Plugin {self.id!r}"
        )
        if self._jobs is not None:
            assigned = JobRegistry.from_declaration(
                self._jobs, path=f"Plugin {self.id!r}"
            )
            if name in assigned:
                raise QgisSdkDeclarationError(
                    f"Plugin {self.id!r}: {name!r} is both assigned in `jobs` and "
                    "declared with @app.job; keep one declaration per name"
                )
        self._declared_jobs = {**self._declared_jobs, name: function}
        return function

    def surface(self, surface: type[S]) -> type[S]:
        """Register a Dialog or Dock class without replacing it."""
        self.add_surface(surface)
        return surface

    def add_surface(self, surface: type[Surface]) -> None:
        from qgis_sdk.ui.surfaces import is_surface_class

        if not is_surface_class(surface):
            raise QgisSdkDeclarationError("surfaces must be Dialog/Dock subclasses")
        self._surfaces.append(surface)

    def add_provider(self, provider: Provider) -> None:
        self._providers.append(provider)

    def include(self, child: QgisSdkPlugin) -> None:
        """Snapshot another plugin's declarations into this plugin atomically."""
        from qgis_sdk.providers import Provider
        from qgis_sdk.ui.surfaces import describe_surface, is_surface_class

        if not isinstance(child, QgisSdkPlugin):
            raise QgisSdkDeclarationError("include requires a QgisSdkPlugin")
        if child.context_factory is not None:
            raise QgisSdkDeclarationError(
                "included plugin cannot have a context_factory"
            )
        pending = [child]
        seen: set[QgisSdkPlugin] = set()
        while pending:
            current = pending.pop()
            if current is self:
                raise QgisSdkDeclarationError("plugin inclusion cycle")
            if current not in seen:
                seen.add(current)
                pending.extend(current._included_plugins)
        members = {child, *child._included_members}
        if members & self._included_members:
            raise QgisSdkDeclarationError("duplicate plugin already included")

        surfaces = [*self._surfaces, *child._surfaces]
        surface_ids: set[str] = set()
        for surface in surfaces:
            if not is_surface_class(surface):
                raise QgisSdkDeclarationError("surfaces must be Dialog/Dock subclasses")
            surface_id = describe_surface(surface).id
            if surface_id in surface_ids:
                raise QgisSdkDeclarationError(f"duplicate surface id {surface_id!r}")
            surface_ids.add(surface_id)
        providers = [*self._providers, *child._providers]
        provider_ids: set[str] = set()
        for provider in providers:
            if not isinstance(provider, Provider):
                raise QgisSdkDeclarationError("providers must be Provider instances")
            if provider.id in provider_ids:
                raise QgisSdkDeclarationError(f"duplicate provider id {provider.id!r}")
            provider_ids.add(provider.id)

        jobs = _merge_jobs(self.jobs, child.jobs)
        self._extend(child._actions)
        self._surfaces = surfaces
        self._providers = providers
        # The merged mapping already holds this plugin's decorator entries.
        self._jobs = jobs
        self._declared_jobs = {}
        self._included_plugins.add(child)
        self._included_members.update(members)

    def describe(self) -> PluginDescription:
        return _describe_lowered_plugin(self._plugin_class())

    def _plugin_class(self) -> type:
        members: dict[str, Any] = {
            "surfaces": tuple(self._surfaces),
            "providers": tuple(self._providers),
        }
        jobs = self.jobs
        if jobs is not None:
            members["jobs"] = jobs
        for id, title, function, events in self._actions:
            if function.__name__ in {
                "surfaces",
                "providers",
                "jobs",
                "ctx",
                "describe",
            } or (function.__name__.startswith("__")):
                raise QgisSdkDeclarationError(
                    "handler name is reserved by the lowered class"
                )
            if (
                not inspect.isfunction(function)
                or (
                    inspect.iscoroutinefunction(function)
                    or inspect.isasyncgenfunction(function)
                )
                or (events is None and inspect.isgeneratorfunction(function))
            ):
                raise QgisSdkDeclarationError(
                    "application accepts only synchronous actions or streams"
                )
            if events is not None and not inspect.isgeneratorfunction(function):
                raise QgisSdkDeclarationError("application streams must be generators")
            signature = inspect.signature(function)
            parameters = list(signature.parameters.values())
            hints = resolve_hints(function, f"action {id} ({function.__name__})")
            if not parameters or hints.get(parameters[0].name) is not PluginContext:
                raise QgisSdkDeclarationError("first argument must be PluginContext")
            if parameters[0].kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                raise QgisSdkDeclarationError("context must be positional")
            if any(parameter.name == "self" for parameter in parameters[1:]):
                raise QgisSdkDeclarationError(
                    "input name self is reserved by class lowering"
                )

            invoke = (
                _lower_handler(function) if events is None else _lower_stream(function)
            )
            invoke.__name__ = function.__name__
            invoke.__signature__ = signature.replace(
                parameters=[
                    inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)
                ]
                + [
                    p.replace(annotation=hints.get(p.name, p.annotation))
                    for p in parameters[1:]
                ],
                return_annotation=hints.get("return", signature.return_annotation),
            )
            invoke.__annotations__ = {
                k: v for k, v in hints.items() if k != parameters[0].name
            }
            if events is None:
                action(id=id, title=title)(invoke)
            else:
                stream(id=id, title=title, events=events)(invoke)
            for attribute in (
                BINDINGS_ATTRIBUTE,
                BINDING_ORDER_ATTRIBUTE,
                WIRES_ATTRIBUTE,
            ):
                if attribute in vars(function):
                    setattr(invoke, attribute, vars(function)[attribute])
            members[function.__name__] = invoke
        return plugin(id=self.id, title=self.title)(
            type("_ApplicationPlugin", (), members)
        )


def _describe_function(function):
    entry = function.__qgis_sdk_app_action__
    app = QgisSdkPlugin(id="application.description", title="Application description")
    app._actions = [entry]
    description = app.describe()
    return description.actions[0] if entry[3] is None else description.streams[0]


# Register object and function descriptions with the shared dispatcher.
register_describer("__qgis_sdk_app_action__", _describe_function)
register_predicate_describer(
    lambda target: isinstance(target, QgisSdkPlugin), lambda app: app.describe()
)


def _merge_jobs(current: Any, incoming: Any) -> Any:
    """Combine two plugins' job declarations, refusing a shared name or id.

    Both sides are read through the same validation the runtime uses, so what
    ``include`` merges is exactly what the included plugin would have exposed -
    not a second, looser reading of the attribute.
    """
    if current is None:
        return incoming
    if incoming is None:
        return current
    from qgis_sdk.jobs import JobRegistry

    left = JobRegistry.from_declaration(current, path="the including plugin")
    right = JobRegistry.from_declaration(incoming, path="the included plugin")
    merged = {name: left.function(name) for name in left.names}
    ids = {description.id for description in left.descriptions()}
    for name in right.names:
        if name in merged:
            raise QgisSdkDeclarationError(f"duplicate job name {name!r}")
        description = right.description(name)
        if description.id in ids:
            raise QgisSdkDeclarationError(f"duplicate job id {description.id!r}")
        ids.add(description.id)
        merged[name] = right.function(name)
    return merged
