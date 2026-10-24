"""QGIS-free experimental declaration metadata and description generation."""

import inspect
import json
import re
from collections.abc import Callable
from dataclasses import MISSING, dataclass, fields, is_dataclass
from types import UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from .models import MAX_SAFE_INTEGER, QgisSdkError

T = TypeVar("T")

#: The event kinds a stream may declare: the same three the frame carries
#: (``qgis_sdk.bridge.streams.StreamEventType``), spelled here so a declaration
#: module never has to import the bridge.
STREAM_EVENT_KINDS = ("data", "progress", "state")

#: Version of the plugin-description wire contract. It is deliberately not the
#: package version: the bridge mirrors this number, and a release that changes a
#: serialized shape has to move it for both sides at once.
PLUGIN_DESCRIPTION_SCHEMA_VERSION = 1


class QgisSdkDeclarationError(QgisSdkError):
    """A declaration cannot be represented in the versioned contract."""

    code = "invalid_declaration"


@dataclass(frozen=True)
class _Metadata:
    id: str
    title: str


def _metadata(id: str, title: str) -> _Metadata:
    if not isinstance(id, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", id):
        raise QgisSdkDeclarationError(
            f"Invalid declaration id {id!r}: use a letter followed by letters, digits, _, . or -"
        )
    if not isinstance(title, str) or not title.strip():
        raise QgisSdkDeclarationError(f"{id}: title must be a nonempty string")
    return _Metadata(id, title)


def plugin(*, id: str, title: str) -> Callable[[type[T]], type[T]]:
    """Attach plugin metadata without wrapping or constructing the class."""
    metadata = _metadata(id, title)

    def decorate(cls: type[T]) -> type[T]:
        if not inspect.isclass(cls):
            raise QgisSdkDeclarationError("@plugin requires a class")
        if "__qgis_sdk_plugin__" in vars(cls):
            raise QgisSdkDeclarationError(f"{id}: duplicate @plugin declaration")
        cls.__qgis_sdk_plugin__ = metadata
        return cls

    return decorate


def action(*, id: str, title: str) -> Callable[[T], T]:
    """Attach allowlisted action metadata to an ordinary instance method."""
    metadata = _metadata(id, title)

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@action requires an instance method")
        _require_undeclared(method, id, "@action")
        method.__qgis_sdk_action__ = metadata
        return method

    return decorate


@dataclass(frozen=True)
class _StreamMetadata(_Metadata):
    events: dict[str, Any]


def stream(*, id: str, title: str, events: Any) -> Callable[[T], T]:
    """Attach stream metadata to an instance method that produces events.

    ``events`` maps each event kind the stream emits (``data``, ``progress``,
    ``state``) to the annotation of that kind's payload. It is the declaration of
    the wire (decision-28): the method's parameters are the subscribe request,
    its return annotation is not described (it still has to resolve, like every
    annotation), and a kind the map does not name is one the host refuses to
    emit.
    """
    metadata = _metadata(id, title)
    if not isinstance(events, dict):
        raise QgisSdkDeclarationError(f"{id}: events must be a mapping of kind to type")
    if not events:
        raise QgisSdkDeclarationError(
            f"{id}: a stream declares at least one event kind"
        )
    for kind in events:
        if kind not in STREAM_EVENT_KINDS:
            raise QgisSdkDeclarationError(
                f"{id}: {kind!r} is not a stream event kind; "
                f"use one of {', '.join(STREAM_EVENT_KINDS)}"
            )
    declared = _StreamMetadata(metadata.id, metadata.title, dict(events))

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@stream requires an instance method")
        _require_undeclared(method, id, "@stream")
        method.__qgis_sdk_stream__ = declared
        return method

    return decorate


def _require_undeclared(method: Any, id: str, decorator: str) -> None:
    """One method is one operation: it cannot be an action and a stream at once."""
    for marker in ("__qgis_sdk_action__", "__qgis_sdk_stream__"):
        if hasattr(method, marker):
            raise QgisSdkDeclarationError(f"{id}: duplicate {decorator} declaration")


@dataclass(frozen=True)
class ActionDescription:
    """Serializable action structure; handler is a binding name, not a callable."""

    id: str
    title: str
    handler: str
    request: dict[str, Any]
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return an independent JSON-compatible value."""
        return json.loads(json.dumps(vars(self), allow_nan=False))


@dataclass(frozen=True)
class StreamDescription:
    """Serializable stream structure: a request in, declared event kinds out.

    ``events`` maps each declared kind to the schema of its payload. There is no
    ``result``: the reply to a subscription is the protocol's acknowledgement,
    not something an author declares (decision-28).
    """

    id: str
    title: str
    handler: str
    request: dict[str, Any]
    events: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Return an independent JSON-compatible value."""
        return json.loads(json.dumps(vars(self), allow_nan=False))


@dataclass(frozen=True)
class PluginDescription:
    """Version 1 description, independent of SDK and future bridge versions."""

    id: str
    title: str
    actions: tuple[ActionDescription, ...]
    schema_version: int = PLUGIN_DESCRIPTION_SCHEMA_VERSION
    streams: tuple[StreamDescription, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "actions": [action.to_dict() for action in self.actions],
            "streams": [item.to_dict() for item in self.streams],
        }

    def to_json(self) -> str:
        """Produce canonical key ordering with no nonfinite JSON numbers."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )


def _object_schema(properties: dict, required: list[str]) -> dict[str, Any]:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def _hints(target: Any, path: str) -> dict[str, Any]:
    try:
        return get_type_hints(target, include_extras=True)
    except (NameError, TypeError) as error:
        raise QgisSdkDeclarationError(
            f"{path}: cannot resolve annotations: {error}"
        ) from error


# Matched by identity rather than lookup: an Annotated extra can be an unhashable
# object, and a dict lookup would raise on the very declarations this must reject.
_PRIMITIVE_JSON_TYPES: dict[Any, str] = {
    str: "string",
    bool: "boolean",
    float: "number",
    int: "integer",
    type(None): "null",
    None: "null",
}


def _schema(
    annotation: Any, path: str, *, result: bool, stack: tuple = ()
) -> dict[str, Any]:
    """Describe one annotation using the JSON Schema subset the contract allows."""
    if get_origin(annotation) is Annotated:
        # `Annotated[T, ...]` stores a T: the extras are host hints (which widget
        # a field deserves), not part of the wire shape. Describing the underlying
        # type keeps one subset instead of a second schema dialect.
        return _schema(get_args(annotation)[0], path, result=result, stack=stack)
    primitive = next(
        (name for cls, name in _PRIMITIVE_JSON_TYPES.items() if annotation is cls),
        None,
    )
    if primitive is not None:
        return _primitive_schema(annotation, primitive)
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        return {
            "anyOf": [_schema(arg, path, result=result, stack=stack) for arg in args]
        }
    if origin is list and len(args) == 1:
        return {
            "type": "array",
            "items": _schema(args[0], path + "[]", result=result, stack=stack),
        }
    if origin is tuple:
        # Deliberately not folded into the list case above: `tuple[str]` would
        # otherwise match it and describe a fixed-length one-element tuple as an
        # unrestricted string array.
        return _tuple_schema(args, path, result=result, stack=stack)
    if origin is Literal:
        return _literal_schema(args, path)
    if inspect.isclass(annotation) and is_dataclass(annotation):
        return _dataclass_schema(annotation, path, result=result, stack=stack)
    raise QgisSdkDeclarationError(
        f"{path}: unsupported annotation {annotation!r}; use JSON primitives, "
        "list, tuple[X, ...], union, Literal or a dataclass"
    )


def _tuple_schema(
    args: tuple, path: str, *, result: bool, stack: tuple
) -> dict[str, Any]:
    """Describe the variadic tuple form, which maps onto the wire's array.

    A tuple is immutable, so it is the honest spelling for a collection inside a
    frozen value DTO. JSON has one array type, so ``tuple[X, ...]`` and ``list[X]``
    produce identical schemas. The fixed-length form has no counterpart: the wire
    cannot carry "exactly two elements of different types" without either dropping
    the length or inventing a branch, so it is refused rather than loosened.
    """
    if len(args) != 2 or args[1] is not Ellipsis:
        raise QgisSdkDeclarationError(
            f"{path}: only the variadic tuple[X, ...] is supported; "
            "a fixed-length tuple has no JSON array equivalent"
        )
    return {
        "type": "array",
        "items": _schema(args[0], path + "[]", result=result, stack=stack),
    }


def _primitive_schema(annotation: Any, json_type: str) -> dict[str, Any]:
    """Bound integers to the magnitude a JavaScript peer reads back exactly."""
    if annotation is not int:
        return {"type": json_type}
    return {
        "type": json_type,
        "minimum": -MAX_SAFE_INTEGER,
        "maximum": MAX_SAFE_INTEGER,
    }


def _literal_schema(args: tuple[Any, ...], path: str) -> dict[str, Any]:
    """Enumerate literal values the wire can carry without reinterpretation."""
    if not all(type(value) in (str, int, bool, type(None)) for value in args):
        raise QgisSdkDeclarationError(
            f"{path}: Literal supports only JSON strings, safe integers, booleans and null"
        )
    if any(type(value) is int and abs(value) > MAX_SAFE_INTEGER for value in args):
        raise QgisSdkDeclarationError(
            f"{path}: Literal integer exceeds the safe-integer range"
        )
    return {"enum": list(args)}


def _dataclass_schema(
    annotation: type[Any], path: str, *, result: bool, stack: tuple
) -> dict[str, Any]:
    """Describe a declared dataclass, refusing a cycle the wire cannot express."""
    if annotation in stack:
        raise QgisSdkDeclarationError(
            f"{path}: recursive dataclasses are not supported"
        )
    hints = _hints(annotation, path)
    properties, required = {}, []
    for field in fields(annotation):
        properties[field.name] = _schema(
            hints[field.name],
            f"{path}.{field.name}",
            result=result,
            stack=(*stack, annotation),
        )
        if result or (field.default is MISSING and field.default_factory is MISSING):
            required.append(field.name)
    return _object_schema(properties, required)


def _require_plain_method(method: Any, path: str, *, generator: bool = False) -> None:
    """Refuse anything that would borrow the host's loop instead of the SDK's.

    A stream may be a generator function - that is the natural way to produce
    events the dispatcher pulls - but neither kind of operation may be a
    coroutine or an async generator.
    """
    if (
        not inspect.isfunction(method)
        or inspect.iscoroutinefunction(method)
        or (inspect.isgeneratorfunction(method) and not generator)
        or inspect.isasyncgenfunction(method)
    ):
        raise QgisSdkDeclarationError(
            f"{path}: requires an ordinary synchronous instance method"
        )


def _require_self_first(parameters: list[Any], path: str) -> None:
    """Require a bound method, so the descriptor is per plugin instance."""
    if (
        not parameters
        or parameters[0].name != "self"
        or parameters[0].kind
        not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        )
    ):
        raise QgisSdkDeclarationError(f"{path}: first parameter must be self")


def _action_inputs(
    parameters: list[Any], hints: dict[str, Any], path: str
) -> tuple[dict[str, Any], list[str]]:
    """Describe the accepted inputs and say which of them must arrive."""
    properties, required = {}, []
    for parameter in parameters:
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise QgisSdkDeclarationError(
                f"{path}.{parameter.name}: variadic and positional-only inputs are unsupported"
            )
        properties[parameter.name] = _schema(
            hints.get(parameter.name, inspect.Signature.empty),
            f"{path}.{parameter.name}",
            result=False,
        )
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
    return properties, required


def _describe_action(
    name: str, method: Any, declaration: _Metadata
) -> ActionDescription:
    path = f"action {declaration.id} ({name})"
    _require_plain_method(method, path)
    parameters = list(inspect.signature(method).parameters.values())
    _require_self_first(parameters, path)
    hints = _hints(method, path)
    properties, required = _action_inputs(parameters[1:], hints, path)
    result = _schema(
        hints.get("return", inspect.Signature.empty), f"{path}.return", result=True
    )
    return ActionDescription(
        declaration.id,
        declaration.title,
        name,
        _object_schema(properties, required),
        result,
    )


def _describe_stream(
    name: str, method: Any, declaration: _StreamMetadata
) -> StreamDescription:
    path = f"stream {declaration.id} ({name})"
    _require_plain_method(method, path, generator=True)
    parameters = list(inspect.signature(method).parameters.values())
    _require_self_first(parameters, path)
    hints = _hints(method, path)
    properties, required = _action_inputs(parameters[1:], hints, path)
    events = {
        kind: _schema(annotation, f"{path}.events.{kind}", result=True)
        for kind, annotation in declaration.events.items()
    }
    return StreamDescription(
        declaration.id,
        declaration.title,
        name,
        _object_schema(properties, required),
        events,
    )


def describe_plugin(cls: type) -> PluginDescription:
    """Inspect trusted author code without constructing it or invoking handlers.

    Annotation resolution may evaluate forward references; this is not a sandbox
    for untrusted Python modules. Dataclass default factories are never called.

    Actions and streams share one id namespace (decision-28): the dispatcher
    allowlists both by id, so a duplicate across the two is refused here.
    """
    if not inspect.isclass(cls) or "__qgis_sdk_plugin__" not in vars(cls):
        raise QgisSdkDeclarationError("describe_plugin requires a class with @plugin")
    metadata = vars(cls)["__qgis_sdk_plugin__"]
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
        metadata.id,
        metadata.title,
        tuple(sorted(actions, key=lambda item: item.id)),
        streams=tuple(sorted(streams, key=lambda item: item.id)),
    )
