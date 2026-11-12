"""Describers: from a decorated class to its description, with the registry."""

import inspect
from collections.abc import Callable
from typing import (
    Any,
)

from qgis_sdk.declarations._contract import QgisSdkDeclarationError
from qgis_sdk.declarations._descriptions import (
    ActionDescription,
    PluginDescription,
    StreamDescription,
)
from qgis_sdk.declarations._metadata import WIRES_ATTRIBUTE, Metadata, declared_metadata
from qgis_sdk.declarations._plugin import PLUGIN_ATTRIBUTE, _StreamMetadata, bindings_of
from qgis_sdk.declarations._schemas import (
    _schema,
    keyword_inputs,
    object_schema,
    require_plain_method,
    require_self_first,
    resolve_hints,
)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_describe_plugin_p1(_s):
    _s.method = (
        _s.member.__func__
        if isinstance(_s.member, (staticmethod, classmethod))
        else _s.member
    )
    if isinstance(_s.member, property):
        _s.method = _s.member.fget
    if not inspect.isfunction(_s.method):
        return _CcContinue()
    _s.declaration = getattr(_s.method, "__qgis_sdk_action__", None)
    _s.streamed = getattr(_s.method, "__qgis_sdk_stream__", None)
    _s.declared = _s.declaration if _s.declaration is not None else _s.streamed


def _cc_describe_plugin_p2(_s):
    if _s.declared is None:
        return _CcContinue()
    if _s.declared.id in _s.ids:
        raise QgisSdkDeclarationError(
            f"{'stream' if _s.declaration is None else 'action'} {_s.declared.id}: "
            f"duplicate id at {_s.name}"
        )
    _s.ids.add(_s.declared.id)
    if _s.declaration is not None:
        _s.actions.append(_describe_action(_s.name, _s.member, _s.declaration))
    else:
        _s.streams.append(_describe_stream(_s.name, _s.member, _s.streamed))


def _cc_describe_plugin_p3(_s):
    _s.own = declared_metadata(_s.cls, PLUGIN_ATTRIBUTE, "describe_plugin", "@plugin")
    _s.members = {}
    for base in reversed(_s.cls.__mro__):
        _s.base = base
        _s.members.update(vars(_s.base))
    _s.actions: list[ActionDescription] = []
    _s.streams: list[StreamDescription] = []
    _s.ids: set[str] = set()


def _cc_describe_plugin_p4(_s):
    for name, member in _s.members.items():
        _s.name = name
        _s.member = member
        _a = None
        for _p in (_cc_describe_plugin_p1, _cc_describe_plugin_p2):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
            if isinstance(_r, (_CcBreak, _CcContinue)):
                _a = _r
                break
        if isinstance(_a, _CcBreak):
            break
        if isinstance(_a, _CcContinue):
            continue


def _cc_describe_plugin_p5(_s):
    return _CcReturn(_describe_plugin_phase1(_s.actions, _s.own, _s.streams))


def _describe_facts1(cls):
    if not (inspect.isclass(cls) or inspect.isfunction(cls)):
        raise QgisSdkDeclarationError(
            "describe requires a QgisSdkPlugin, a declared function or surface, or a Provider"
        )
    raise QgisSdkDeclarationError(
        "describe requires a QgisSdkPlugin, a function registered as an action or stream, "
        "a job, algorithm, provider, UI surface or wired UI handler"
    )


def _describe_plugin_phase1(actions, own, streams):
    return PluginDescription(
        own.id,
        own.title,
        tuple(sorted(actions, key=lambda item: item.id)),
        streams=tuple(sorted(streams, key=lambda item: item.id)),
    )


def _describe_action(
    name: str, method: Any, declaration: Metadata
) -> ActionDescription:
    path = f"action {declaration.id} ({name})"
    require_plain_method(method, path)
    parameters = list(inspect.signature(method).parameters.values())
    require_self_first(parameters, path)
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
        bindings=bindings_of(method),
        wires=tuple(vars(method).get(WIRES_ATTRIBUTE, ())),
    )


def _describe_stream(
    name: str, method: Any, declaration: _StreamMetadata
) -> StreamDescription:
    path = f"stream {declaration.id} ({name})"
    require_plain_method(method, path, generator=True)
    parameters = list(inspect.signature(method).parameters.values())
    require_self_first(parameters, path)
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
        wires=tuple(vars(method).get(WIRES_ATTRIBUTE, ())),
    )


def type_name(annotation: Any) -> str:
    """The short name a message or a transport view uses for a type."""
    return getattr(annotation, "__name__", str(annotation))


_DESCRIBERS: dict[str, Callable[[Any], Any]] = {}
_PREDICATE_DESCRIBERS: list[tuple[Callable[[Any], bool], Callable[[Any], Any]]] = []
_DESCRIBER_ENRICHERS: dict[str, Callable[[Any, Any], Any]] = {}


def register_describer(attribute: str, describer: Callable[[Any], Any]) -> None:
    """Teach :func:`describe` the marker a decorator sets and who reads it.

    Each decorating module registers itself when imported; a class can only
    carry a marker if that module ran, so ``describe`` never needs to import
    a higher layer.
    """
    _DESCRIBERS[attribute] = describer


def register_predicate_describer(
    predicate: Callable[[Any], bool], describer: Callable[[Any], Any]
) -> None:
    """Register an object-kind describer without importing higher layers."""
    _PREDICATE_DESCRIBERS.append((predicate, describer))


def register_describer_enricher(
    attribute: str, enricher: Callable[[Any, Any], Any]
) -> None:
    """Enrich unified introspection without changing a lower-layer wire schema."""
    _DESCRIBER_ENRICHERS[attribute] = enricher


def describe(cls: Any) -> Any:
    """Describe a plugin, action, stream, job, algorithm, provider or UI surface.

    A decorated UI handler describes its wires. Action and surface descriptions
    expose stacked bindings; plugin descriptions expose their registered surfaces
    and bindings through ``bindings``. These host metadata fields are not part
    of bridge serialization. Description inspects trusted author code and may
    resolve/evaluate type annotations; it never invokes the target handler.
    """
    if inspect.ismethod(cls):
        cls = cls.__func__
    if inspect.isclass(cls) and PLUGIN_ATTRIBUTE in vars(cls):
        raise QgisSdkDeclarationError(
            "describe requires a QgisSdkPlugin, not a plugin class"
        )
    if inspect.isclass(cls) or inspect.isfunction(cls):
        for attribute, describer in _DESCRIBERS.items():
            if attribute in vars(cls):
                result = describer(cls)
                enrich = _DESCRIBER_ENRICHERS.get(attribute)
                return enrich(cls, result) if enrich is not None else result
    for predicate, describer in _PREDICATE_DESCRIBERS:
        if predicate(cls):
            return describer(cls)
    _describe_facts1(cls)


def describe_plugin(cls: type) -> PluginDescription:
    """Inspect trusted author code without constructing it or invoking handlers.

    Annotation resolution may evaluate forward references; this is not a sandbox
    for untrusted Python modules. Dataclass default factories are never called.

    Actions and streams share one id namespace (decision-28): the dispatcher
    allowlists both by id, so a duplicate across the two is refused here.
    """
    _s = _CcState(cls=cls)
    for _p in (_cc_describe_plugin_p3, _cc_describe_plugin_p4, _cc_describe_plugin_p5):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def describe_lowered_plugin(cls: type) -> PluginDescription:
    """Describe and enrich an internally lowered application class."""
    result = describe_plugin(cls)
    enrich = _DESCRIBER_ENRICHERS.get(PLUGIN_ATTRIBUTE)
    return enrich(cls, result) if enrich is not None else result


def _describe_action_function(method: Any) -> ActionDescription:
    return _describe_action(method.__name__, method, method.__qgis_sdk_action__)


def _describe_stream_function(method: Any) -> StreamDescription:
    return _describe_stream(method.__name__, method, method.__qgis_sdk_stream__)


register_describer("__qgis_sdk_action__", _describe_action_function)
register_describer("__qgis_sdk_stream__", _describe_stream_function)
