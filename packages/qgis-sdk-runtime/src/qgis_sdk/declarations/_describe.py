"""Describers: from a decorated class to its description, with the registry."""

import inspect
from collections.abc import Callable
from typing import (
    Any,
)

from qgis_sdk.declarations._contract import QgisSdkDeclarationError
from qgis_sdk.declarations._descriptions import (
    ActionDescription,
    Description,
    PluginDescription,
    StreamDescription,
)
from qgis_sdk.declarations._metadata import Metadata, declared_metadata
from qgis_sdk.declarations._plugin import PLUGIN_ATTRIBUTE, _StreamMetadata
from qgis_sdk.declarations._schemas import (
    _require_plain_method,
    _require_self_first,
    _schema,
    keyword_inputs,
    object_schema,
    resolve_hints,
)


def _describe_action(
    name: str, method: Any, declaration: Metadata
) -> ActionDescription:
    path = f"action {declaration.id} ({name})"
    _require_plain_method(method, path)
    parameters = list(inspect.signature(method).parameters.values())
    _require_self_first(parameters, path)
    hints = resolve_hints(method, path)
    properties, required = keyword_inputs(parameters[1:], hints, path)
    result = _schema(
        hints.get("return", inspect.Signature.empty), f"{path}.return", result=True
    )
    return ActionDescription(
        declaration.id,
        declaration.title,
        name,
        object_schema(properties, required),
        result,
    )


def _describe_stream(
    name: str, method: Any, declaration: _StreamMetadata
) -> StreamDescription:
    path = f"stream {declaration.id} ({name})"
    _require_plain_method(method, path, generator=True)
    parameters = list(inspect.signature(method).parameters.values())
    _require_self_first(parameters, path)
    hints = resolve_hints(method, path)
    properties, required = keyword_inputs(parameters[1:], hints, path)
    events = {
        kind: _schema(annotation, f"{path}.events.{kind}", result=True)
        for kind, annotation in declaration.events.items()
    }
    return StreamDescription(
        declaration.id,
        declaration.title,
        name,
        object_schema(properties, required),
        events,
    )


def type_name(annotation: Any) -> str:
    """The short name a message or a transport view uses for a type."""
    return getattr(annotation, "__name__", str(annotation))


_DESCRIBERS: dict[str, Callable[[type], Description]] = {}


def register_describer(
    attribute: str, describer: Callable[[type], Description]
) -> None:
    """Teach :func:`describe` the marker a decorator sets and who reads it.

    Each decorating module registers itself when imported; a class can only
    carry a marker if that module ran, so ``describe`` never needs to import
    a higher layer.
    """
    _DESCRIBERS[attribute] = describer


def describe(cls: Any) -> Description:
    """Describe whatever ``cls`` declares - a plugin class, a job or an algorithm.

    The narrow forms (``describe_plugin`` and friends) return the concrete type;
    this one answers for any decorated class or job function and returns the
    protocol.
    """
    if not (inspect.isclass(cls) or inspect.isfunction(cls)):
        raise QgisSdkDeclarationError("describe requires a class or a function")
    for attribute, describer in _DESCRIBERS.items():
        if attribute in vars(cls):
            return describer(cls)
    raise QgisSdkDeclarationError(
        "describe requires a class declared with @plugin, or a function "
        "declared with @job or @provider.algorithm"
    )


def describe_plugin(cls: type) -> PluginDescription:
    """Inspect trusted author code without constructing it or invoking handlers.

    Annotation resolution may evaluate forward references; this is not a sandbox
    for untrusted Python modules. Dataclass default factories are never called.

    Actions and streams share one id namespace (decision-28): the dispatcher
    allowlists both by id, so a duplicate across the two is refused here.
    """
    own = declared_metadata(cls, PLUGIN_ATTRIBUTE, "describe_plugin", "@plugin")
    members = {}
    for base in reversed(cls.__mro__):
        members.update(vars(base))
    actions: list[ActionDescription] = []
    streams: list[StreamDescription] = []
    ids: set[str] = set()
    for name, member in members.items():
        method = (
            member.__func__
            if isinstance(member, (staticmethod, classmethod))
            else member
        )
        if isinstance(member, property):
            method = member.fget
        if not inspect.isfunction(method):
            continue
        declaration = getattr(method, "__qgis_sdk_action__", None)
        streamed = getattr(method, "__qgis_sdk_stream__", None)
        declared = declaration if declaration is not None else streamed
        if declared is None:
            continue
        if declared.id in ids:
            raise QgisSdkDeclarationError(
                f"{'stream' if declaration is None else 'action'} {declared.id}: "
                f"duplicate id at {name}"
            )
        ids.add(declared.id)
        if declaration is not None:
            actions.append(_describe_action(name, member, declaration))
        else:
            streams.append(_describe_stream(name, member, streamed))
    return PluginDescription(
        own.id,
        own.title,
        tuple(sorted(actions, key=lambda item: item.id)),
        streams=tuple(sorted(streams, key=lambda item: item.id)),
    )


register_describer(PLUGIN_ATTRIBUTE, describe_plugin)
