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
    Protocol,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    runtime_checkable,
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
class Metadata:
    """What every declaration decorator records: a validated id and a title."""

    id: str
    title: str


def metadata(id: str, title: str) -> Metadata:
    """Validate the id and title every ``@plugin``/``@algorithm``/``@job`` takes."""
    if not isinstance(id, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", id):
        raise QgisSdkDeclarationError(
            f"Invalid declaration id {id!r}: use a letter followed by letters, digits, _, . or -"
        )
    if not isinstance(title, str) or not title.strip():
        raise QgisSdkDeclarationError(f"{id}: title must be a nonempty string")
    return Metadata(id, title)


def mark_class(cls: Any, attribute: str, declared: Metadata, decorator: str) -> None:
    """Record ``declared`` on ``cls`` under ``attribute`` - the one marker pattern.

    The class is left otherwise untouched: no base class, no injected method
    (decision-6, decision-10). A marker set on a parent is not the child's own
    declaration, which is why every describer reads ``vars(cls)`` and not
    ``getattr``.
    """
    if not inspect.isclass(cls):
        raise QgisSdkDeclarationError(f"{decorator} requires a class")
    if attribute in vars(cls):
        raise QgisSdkDeclarationError(
            f"{declared.id}: duplicate {decorator} declaration"
        )
    setattr(cls, attribute, declared)


def declare_class(
    attribute: str, decorator: str, *, id: str, title: str
) -> Callable[[type[T]], type[T]]:
    """Build the class decorator ``@plugin``, ``@algorithm`` and ``@job`` all are."""
    declared = metadata(id, title)

    def decorate(cls: type[T]) -> type[T]:
        mark_class(cls, attribute, declared, decorator)
        return cls

    return decorate


def declared_metadata(
    cls: Any, attribute: str, describer: str, decorator: str
) -> Metadata:
    """Return the class's own marker, or refuse with the describer's message."""
    if not inspect.isclass(cls) or attribute not in vars(cls):
        raise QgisSdkDeclarationError(f"{describer} requires a class with {decorator}")
    declared = vars(cls)[attribute]
    if not isinstance(declared, Metadata):
        raise QgisSdkDeclarationError(f"{describer} requires a class with {decorator}")
    return declared


PLUGIN_ATTRIBUTE = "__qgis_sdk_plugin__"


def plugin(*, id: str, title: str) -> Callable[[type[T]], type[T]]:
    """Attach plugin metadata without wrapping or constructing the class."""
    return declare_class(PLUGIN_ATTRIBUTE, "@plugin", id=id, title=title)


def action(*, id: str, title: str) -> Callable[[T], T]:
    """Attach allowlisted action metadata to an ordinary instance method."""
    declared = metadata(id, title)

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@action requires an instance method")
        _require_undeclared(method, id, "@action")
        method.__qgis_sdk_action__ = declared
        return method

    return decorate


@dataclass(frozen=True)
class _StreamMetadata(Metadata):
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
    declared = metadata(id, title)
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
    streamed = _StreamMetadata(declared.id, declared.title, dict(events))

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@stream requires an instance method")
        _require_undeclared(method, id, "@stream")
        method.__qgis_sdk_stream__ = streamed
        return method

    return decorate


def _require_undeclared(method: Any, id: str, decorator: str) -> None:
    """One method is one operation: it cannot be an action and a stream at once."""
    for marker in ("__qgis_sdk_action__", "__qgis_sdk_stream__"):
        if hasattr(method, marker):
            raise QgisSdkDeclarationError(f"{id}: duplicate {decorator} declaration")


def canonical_json(value: Any) -> str:
    """The one JSON form every description and fingerprint uses.

    Sorted keys and compact separators make two equal descriptions two equal
    strings, and ``allow_nan=False`` keeps a nonfinite number from becoming a
    token no JSON parser accepts.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_copy(value: Any) -> Any:
    """Return an independent JSON-compatible copy, refusing nonfinite numbers."""
    return json.loads(json.dumps(value, allow_nan=False))


@runtime_checkable
class Description(Protocol):
    """What every description object offers, whatever it describes.

    ``PluginDescription``, ``AlgorithmDescription``, ``JobDescription`` and
    ``ProviderDescription`` all satisfy it; generators and the bridge consume
    this shape rather than one of the concrete types.
    """

    @property
    def id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def schema_version(self) -> int: ...

    def to_dict(self) -> dict[str, Any]: ...

    def to_json(self) -> str: ...


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
        return _json_copy(vars(self))


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
        return _json_copy(vars(self))


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
        return canonical_json(self.to_dict())


def _object_schema(properties: dict, required: list[str]) -> dict[str, Any]:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def resolve_hints(target: Any, path: str) -> dict[str, Any]:
    """Resolve ``target``'s annotations, naming ``path`` when one cannot be."""
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


def schema_for(annotation: Any, path: str, *, result: bool) -> dict[str, Any]:
    """Describe one annotation using the JSON Schema subset the contract allows."""
    return _schema(annotation, path, result=result)


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
    hints = resolve_hints(annotation, path)
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
    name: str, method: Any, declaration: Metadata
) -> ActionDescription:
    path = f"action {declaration.id} ({name})"
    _require_plain_method(method, path)
    parameters = list(inspect.signature(method).parameters.values())
    _require_self_first(parameters, path)
    hints = resolve_hints(method, path)
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
    hints = resolve_hints(method, path)
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


@dataclass(frozen=True)
class RunSignature:
    """What ``@algorithm`` and ``@job`` classes declare through their ``run``."""

    metadata: Metadata
    inputs_type: Any
    result_type: Any
    inputs_schema: dict[str, Any]
    result_schema: dict[str, Any]
    asynchronous: bool


def describe_run_method(cls: Any, attribute: str, kind: str) -> RunSignature:
    """Inspect a ``run(self, inputs) -> Result`` class without constructing it.

    ``kind`` is the noun the messages use (``"algorithm"``, ``"job"``); the
    decorator and describer names follow from it. The schemas come from the
    same generator the plugin declarations use, so a type the contract cannot
    express fails here, at inspection time, rather than during a run.
    """
    declared = declared_metadata(cls, attribute, f"describe_{kind}", f"@{kind}")
    run = vars(cls).get("run")
    article = "an" if kind[:1] in "aeiou" else "a"
    if not inspect.isfunction(run):
        raise QgisSdkDeclarationError(
            f"{declared.id}: {article} {kind} needs its own run method"
        )
    parameters = list(inspect.signature(run).parameters.values())
    if len(parameters) != 2 or parameters[0].name != "self":
        raise QgisSdkDeclarationError(
            f"{declared.id}: run takes self and exactly one typed inputs argument"
        )
    # Resolved, not raw: a module using `from __future__ import annotations`
    # hands us strings, and a forward reference has to be evaluated the same way
    # a plugin action's annotations are.
    hints = resolve_hints(run, f"{kind} {declared.id}")
    inputs_type = hints.get(parameters[1].name, inspect.Parameter.empty)
    result_type = hints.get("return", inspect.Signature.empty)
    if inputs_type is inspect.Parameter.empty:
        raise QgisSdkDeclarationError(f"{declared.id}: run inputs must be annotated")
    if result_type is inspect.Signature.empty:
        raise QgisSdkDeclarationError(f"{declared.id}: run must declare its result")
    return RunSignature(
        metadata=declared,
        inputs_type=inputs_type,
        result_type=result_type,
        inputs_schema=schema_for(inputs_type, f"{declared.id}.inputs", result=False),
        result_schema=schema_for(result_type, f"{declared.id}.result", result=True),
        asynchronous=inspect.iscoroutinefunction(run),
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


def describe(cls: type) -> Description:
    """Describe whatever ``cls`` declares - plugin, algorithm or job.

    The narrow forms (``describe_plugin`` and friends) return the concrete type;
    this one answers for any decorated class and returns the protocol.
    """
    if not inspect.isclass(cls):
        raise QgisSdkDeclarationError("describe requires a class")
    for attribute, describer in _DESCRIBERS.items():
        if attribute in vars(cls):
            return describer(cls)
    raise QgisSdkDeclarationError(
        "describe requires a class declared with @plugin, @algorithm or @job"
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
