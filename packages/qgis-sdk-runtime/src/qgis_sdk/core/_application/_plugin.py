"""Explicit plugin declarations and composition."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from qgis_sdk.core.contexts import PluginContext
from qgis_sdk.declarations import (
    BINDING_ORDER_ATTRIBUTE,
    BINDINGS_ATTRIBUTE,
    WIRES_ATTRIBUTE,
    QgisSdkDeclarationError,
    attach_describe,
    resolve_hints,
    validate_given,
)
from qgis_sdk.declarations._plugin import action, stream

if TYPE_CHECKING:
    from qgis_sdk.core._application._sdk_plugin import QgisSdkPlugin


def initial_plugin_fields(self: QgisSdkPlugin) -> None:
    """The mutable declarations a plugin starts with."""
    self._providers: list[Provider] = []
    self._jobs: Any = None
    self._declared_jobs: dict[str, Callable[..., Any]] = {}
    self._included_plugins: set[QgisSdkPlugin] = set()
    self._included_members: set[QgisSdkPlugin] = set()
    self.context_factory: Callable[[object | None], PluginContext] | None = None


def commit_inclusion(
    self: QgisSdkPlugin,
    child: QgisSdkPlugin,
    jobs: Any,
    members: set[QgisSdkPlugin],
    providers: list[Provider],
) -> None:
    """Commit the snapshot only after every validation has passed."""
    self._providers = providers
    # The merged mapping already holds this plugin's decorator entries.
    self._jobs = jobs
    self._declared_jobs = {}
    self._included_plugins.add(child)
    self._included_members.update(members)


if TYPE_CHECKING:
    from qgis_sdk.providers import Provider
    from qgis_sdk.ui.surfaces import Surface
F = TypeVar("F", bound=Callable[..., Any])
S = TypeVar("S", bound="Surface")
_Entry = tuple[str, str, Callable[..., Any], dict[str, Any] | None]


def validate_metadata(id: str, title: str) -> None:
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


def _declare_job_function(
    function: Callable[..., Any], id: str | None, title: str | None
) -> None:
    """Apply ``@job`` metadata to a function the author left undecorated."""
    from qgis_sdk.jobs import job as declare_job

    if id is not None or title is not None:
        declare_job(id=id, title=title)(function)
    elif "__qgis_sdk_job__" not in vars(function):
        declare_job(function)


def _job_registry_conflict(
    self: QgisSdkPlugin, name: str, function: Callable[..., Any]
) -> None:
    """One call validates the name, decoration, reserved names and collisions."""
    from qgis_sdk.jobs import JobRegistry

    path = f"Plugin {self.id!r}"
    JobRegistry.from_declaration({**self._declared_jobs, name: function}, path=path)
    if self._jobs is None:
        return
    assigned = JobRegistry.from_declaration(self._jobs, path=path)
    if name in assigned:
        raise QgisSdkDeclarationError(
            f"Plugin {self.id!r}: {name!r} is both assigned in `jobs` and "
            "declared with @app.job; keep one declaration per name"
        )


def register_declared_job(
    self: QgisSdkPlugin,
    function: Callable[..., Any],
    key: str | None,
    id: str | None,
    title: str | None,
) -> Any:
    """Validate and record one decorator-declared job."""
    if not inspect.isfunction(function):
        raise QgisSdkDeclarationError("@app.job declares a function")
    from qgis_sdk.declarations import derive_id

    _declare_job_function(function, id, title)
    name = key if key is not None else derive_id(function.__name__)
    if name in self._declared_jobs:
        raise QgisSdkDeclarationError(
            f"Plugin {self.id!r}: two jobs are named {name!r}; give one of "
            "them another name with @app.job(key=...)"
        )
    _job_registry_conflict(self, name, function)
    self._declared_jobs = {**self._declared_jobs, name: function}
    return function


def include_cycle_free(self: QgisSdkPlugin, child: QgisSdkPlugin) -> set[QgisSdkPlugin]:
    """Walk the child's inclusions; refuse a cycle or an already-included member."""
    from ._sdk_plugin import QgisSdkPlugin

    if not isinstance(child, QgisSdkPlugin):
        raise QgisSdkDeclarationError("include requires a QgisSdkPlugin")
    if child.context_factory is not None:
        raise QgisSdkDeclarationError("included plugin cannot have a context_factory")
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
    return members


def validated_surfaces(
    self: QgisSdkPlugin, child: QgisSdkPlugin
) -> list[type[Surface]]:
    """Both plugins' surfaces, with no invalid class or duplicate id."""
    from qgis_sdk.ui.surfaces import describe_surface, is_surface_class

    surfaces = [*self._surfaces, *child._surfaces]
    surface_ids: set[str] = set()
    for surface in surfaces:
        if not is_surface_class(surface):
            raise QgisSdkDeclarationError("surfaces must be Dialog/Dock subclasses")
        surface_id = describe_surface(surface).id
        if surface_id in surface_ids:
            raise QgisSdkDeclarationError(f"duplicate surface id {surface_id!r}")
        surface_ids.add(surface_id)
    return surfaces


def validated_providers(self: QgisSdkPlugin, child: QgisSdkPlugin) -> list[Provider]:
    """Both plugins' providers, with no wrong type or duplicate id."""
    from qgis_sdk.providers import Provider

    providers = [*self._providers, *child._providers]
    provider_ids: set[str] = set()
    for provider in providers:
        if not isinstance(provider, Provider):
            raise QgisSdkDeclarationError("providers must be Provider instances")
        if provider.id in provider_ids:
            raise QgisSdkDeclarationError(f"duplicate provider id {provider.id!r}")
        provider_ids.add(provider.id)
    return providers


def _validate_handler_shape(
    function: Callable[..., Any], events: dict[str, Any] | None
) -> None:
    """The handler's name and callable kind must fit class lowering."""
    if function.__name__ in {
        "surfaces",
        "providers",
        "jobs",
        "ctx",
        "describe",
    } or (function.__name__.startswith("__")):
        raise QgisSdkDeclarationError("handler name is reserved by the lowered class")
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


def _validate_handler_context(function: Callable[..., Any], id: str) -> None:
    """The first argument is a positional ``PluginContext`` and no input is self."""
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
        raise QgisSdkDeclarationError("input name self is reserved by class lowering")


def validate_handler(
    function: Callable[..., Any], events: dict[str, Any] | None, id: str
) -> None:
    _validate_handler_shape(function, events)
    _validate_handler_context(function, id)


def _handler_signature(function: Callable[..., Any], id: str) -> inspect.Signature:
    """The lowered method's signature: ``self`` plus the resolved input hints."""
    signature = inspect.signature(function)
    parameters = list(signature.parameters.values())
    hints = resolve_hints(function, f"action {id} ({function.__name__})")
    return signature.replace(
        parameters=[inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        + [
            p.replace(annotation=hints.get(p.name, p.annotation))
            for p in parameters[1:]
        ],
        return_annotation=hints.get("return", signature.return_annotation),
    )


def _copy_declaration_attributes(
    function: Callable[..., Any], invoke: Callable[..., Any]
) -> None:
    """Bindings, their order and wires survive the lowering."""
    for attribute in (BINDINGS_ATTRIBUTE, BINDING_ORDER_ATTRIBUTE, WIRES_ATTRIBUTE):
        if attribute in vars(function):
            setattr(invoke, attribute, vars(function)[attribute])


def lowered_handler(
    id: str,
    title: str,
    function: Callable[..., Any],
    events: dict[str, Any] | None,
) -> Callable[..., Any]:
    """One class method, declared as an action or a stream."""
    invoke = _lower_handler(function) if events is None else _lower_stream(function)
    invoke.__name__ = function.__name__
    signature = inspect.signature(function)
    parameters = list(signature.parameters.values())
    hints = resolve_hints(function, f"action {id} ({function.__name__})")
    invoke.__signature__ = _handler_signature(function, id)
    invoke.__annotations__ = {k: v for k, v in hints.items() if k != parameters[0].name}
    if events is None:
        action(id=id, title=title)(invoke)
    else:
        stream(id=id, title=title, events=events)(invoke)
    _copy_declaration_attributes(function, invoke)
    return invoke


class ActionRegistry:
    """A reusable, explicitly included collection of functions."""

    def __init__(self) -> None:
        self._actions: list[_Entry] = []

    def action(self, *, id: str, title: str) -> Callable[[F], F]:
        validate_metadata(id, title)

        def register(function: F) -> F:
            self._register(id, title, function, None)
            return function

        return register

    def stream(
        self, *, id: str, title: str, events: Mapping[str, Any]
    ) -> Callable[[F], F]:
        validate_metadata(id, title)

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
