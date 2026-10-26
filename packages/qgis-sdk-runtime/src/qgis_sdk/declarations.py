"""QGIS-free experimental declaration metadata and description generation."""

import hashlib
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
    """Validate the id and title every ``@plugin``/``@job``/``@provider.algorithm`` takes."""
    _validate_id(id)
    _validate_title(id, title)
    return Metadata(id, title)


def _validate_id(id: Any) -> None:
    if not isinstance(id, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", id):
        raise QgisSdkDeclarationError(
            f"Invalid declaration id {id!r}: use a letter followed by letters, digits, _, . or -"
        )


def _validate_title(id: Any, title: Any) -> None:
    if not isinstance(title, str) or not title.strip():
        raise QgisSdkDeclarationError(f"{id}: title must be a nonempty string")


_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _words(name: str) -> list[str]:
    """Split ``FieldTools``, ``HTTPServer`` or ``list_layers`` into its words."""
    spaced = _WORD_BOUNDARY.sub(" ", name.replace("_", " "))
    return spaced.split()


def derive_id(name: str) -> str:
    """The snake_case id a declaration gets from its Python name.

    ``FieldTools`` becomes ``field_tools`` and ``HTTPServer`` becomes
    ``http_server``; a snake_case method name is kept as it is, minus any
    leading underscores (an id starts with a letter).
    """
    id = "_".join(word.lower() for word in _words(name))
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", id):
        raise QgisSdkDeclarationError(
            f"Cannot derive a declaration id from {name!r}; pass id= explicitly"
        )
    return id


def derive_title(name: str) -> str:
    """The readable title a declaration gets from its Python name.

    A CamelCase name keeps its word casing (``FieldTools`` -> ``Field Tools``);
    a snake_case name reads as a sentence (``list_layers`` -> ``List layers``).
    """
    words = _words(name)
    if not words:
        raise QgisSdkDeclarationError(
            f"Cannot derive a declaration title from {name!r}; pass title= explicitly"
        )
    if any(word[:1].isupper() for word in words):
        return " ".join(words)
    return " ".join([words[0].capitalize(), *words[1:]])


def _class_id_suffix(cls: type) -> str:
    """Six hex digits hashed from the class's module and qualified name.

    The suffix is what keeps two plugins, algorithms or jobs that share a class
    name apart without making the id random: the same class in the same place
    derives the same id on every import, so a generated client and a
    fingerprint stay valid until the class itself moves.
    """
    qualified = f"{cls.__module__}.{cls.__qualname__}"
    return hashlib.sha256(qualified.encode()).hexdigest()[:6]


def _declared_metadata(
    target: Any, id: str | None, title: str | None, *, suffixed: bool
) -> Metadata:
    """Complete a declaration from ``target``'s name where the author left gaps."""
    name = getattr(target, "__name__", None)
    if id is None:
        if not isinstance(name, str):
            raise QgisSdkDeclarationError(
                "cannot derive an id without a name; pass id= explicitly"
            )
        id = derive_id(name)
        if suffixed:
            id = f"{id}_{_class_id_suffix(target)}"
    if title is None:
        if not isinstance(name, str):
            raise QgisSdkDeclarationError(
                f"{id}: cannot derive a title without a name; pass title= explicitly"
            )
        title = derive_title(name)
    return metadata(id, title)


def validate_given(id: str | None, title: str | None) -> None:
    """Refuse a bad explicit id or title at decoration time, before any class exists."""
    if id is not None:
        _validate_id(id)
    if title is not None:
        _validate_title(id if id is not None else "declaration", title)


def class_metadata(cls: type, id: str | None, title: str | None) -> Metadata:
    """The metadata a class declaration carries: given values, or derived ones.

    A derived class id is the snake_case class name plus the module/qualname
    hash suffix; a derived title is the class name spaced into words.
    """
    return _declared_metadata(cls, id, title, suffixed=True)


def function_metadata(function: Any, id: str | None, title: str | None) -> Metadata:
    """The metadata a module-level ``@job`` function declaration carries.

    Derived the way a class id is - snake_case name plus the module/qualname
    suffix - because a job id has to stay unique across modules the same way
    an algorithm id does, and because the two are documented as one rule.
    """
    return _declared_metadata(function, id, title, suffixed=True)


def mark_function(
    function: Any, attribute: str, declared: Metadata, decorator: str
) -> None:
    """Record ``declared`` on a plain function under ``attribute``.

    The function is left otherwise untouched: not wrapped, not bound, no
    attribute beyond the marker (decision-10 applied to functions). A class
    is refused with the way forward, because ``@job`` used to take one.
    """
    if inspect.isclass(function):
        raise QgisSdkDeclarationError(
            f"{decorator} declares a function, not a class: write "
            f"`{decorator} def name(ctx: JobContext, ...) -> Result` "
            "(the class form was removed; see the 0.6.0 migration notes)"
        )
    if not inspect.isfunction(function):
        raise QgisSdkDeclarationError(f"{decorator} requires a function")
    if attribute in vars(function):
        raise QgisSdkDeclarationError(
            f"{declared.id}: duplicate {decorator} declaration"
        )
    setattr(function, attribute, declared)


def declared_function_metadata(
    function: Any, attribute: str, describer: str, decorator: str
) -> Metadata:
    """Return the function's own marker, or refuse with the describer's message."""
    if not inspect.isfunction(function) or attribute not in vars(function):
        raise QgisSdkDeclarationError(
            f"{describer} requires a function with {decorator}"
        )
    declared = vars(function)[attribute]
    if not isinstance(declared, Metadata):
        raise QgisSdkDeclarationError(
            f"{describer} requires a function with {decorator}"
        )
    return declared


def method_metadata(method: Any, id: str | None, title: str | None) -> Metadata:
    """The metadata a method declaration carries: given values, or derived ones.

    A method id is the plain method name: it is already unique inside its class,
    and the bridge client spells it as a property, so no suffix is added.
    """
    return _declared_metadata(method, id, title, suffixed=False)


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
    attribute: str,
    decorator: str,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Callable[[type[T]], type[T]]:
    """Build a marker class decorator of the shape ``@plugin`` has.

    An omitted ``id`` or ``title`` is derived from the class once it is known
    (:func:`class_metadata`); a given one is validated right here.
    """
    validate_given(id, title)

    def decorate(cls: type[T]) -> type[T]:
        if not inspect.isclass(cls):
            raise QgisSdkDeclarationError(f"{decorator} requires a class")
        mark_class(cls, attribute, class_metadata(cls, id, title), decorator)
        return cls

    return decorate


def class_decorator(
    attribute: str,
    decorator: str,
    cls: Any,
    *,
    id: str | None,
    title: str | None,
) -> Any:
    """Serve both ``@plugin`` and ``@plugin(...)`` from one definition.

    Used bare, the decorator receives the class as its only positional
    argument and decorates it at once; called, it returns the decorator.
    """
    decorate = declare_class(attribute, decorator, id=id, title=title)
    if cls is None:
        return decorate
    return decorate(cls)


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
#: An SDK class with this dict describes itself as an action *result* (the
#: handle a job-submitting action returns); ``WIRE_VALUE_METHOD`` is how the
#: dispatcher turns the instance into that JSON.
WIRE_SCHEMA_ATTRIBUTE = "__qgis_sdk_schema__"
WIRE_VALUE_METHOD = "__qgis_sdk_wire__"


def plugin(
    cls: type[T] | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach plugin metadata without wrapping or constructing the class.

    ``@plugin`` alone derives the id (``field_tools_<hash>`` for a class named
    ``FieldTools``) and the title (``Field Tools``); ``id=`` and ``title=``
    override either one.
    """
    decorate = declare_class(PLUGIN_ATTRIBUTE, "@plugin", id=id, title=title)

    def decorate_plugin(target: type[T]) -> type[T]:
        decorate(target)
        validate_plugin_bindings(target)
        return target

    if cls is None:
        return decorate_plugin
    return decorate_plugin(cls)


BINDINGS_ATTRIBUTE = "__qgis_sdk_bindings__"
BINDING_ORDER_ATTRIBUTE = "__qgis_sdk_binding_order__"


def bindings_of(target: object) -> tuple[Any, ...]:
    """The Desktop bindings declared on ``target`` itself (:mod:`qgis_sdk.bindings`).

    Read from ``vars`` so a binding on a parent class is never the child's;
    innermost decorator first, the way the source reads bottom-up.
    """
    if not hasattr(target, "__dict__"):
        return ()
    return tuple(vars(target).get(BINDINGS_ATTRIBUTE, ()))


def refuse_bindings(target: Any, decorator: str) -> None:
    """``@job``/``@stream`` applied over a binding: refuse with the way forward."""
    if bindings_of(target):
        raise QgisSdkDeclarationError(
            f"{decorator} cannot carry a toolbar, menu or shortcut binding "
            f"({target.__name__}); bind an @action instead"
        )


def validate_plugin_bindings(cls: type) -> None:
    """Refuse a plain method that carries a binding, when the class is created.

    Bindings stack on ``@action`` in any order, so a binding applied below
    ``@action`` cannot tell yet; the plugin class is where both are known.
    """
    for name, member in vars(cls).items():
        function = member.__func__ if isinstance(member, staticmethod) else member
        if not inspect.isfunction(function) or not bindings_of(function):
            continue
        if not hasattr(function, "__qgis_sdk_action__"):
            raise QgisSdkDeclarationError(
                f"{cls.__name__}.{name} carries a binding but is not an @action; "
                "add @action (bindings stack on it in any order)"
            )


def action(
    method: T | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach allowlisted action metadata to an ordinary instance method.

    ``@action`` alone names the action after the method (``list_layers``, titled
    ``List layers``); ``id=`` and ``title=`` override either one.
    """
    validate_given(id, title)

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@action requires an instance method")
        declared = method_metadata(method, id, title)
        _require_undeclared(method, declared.id, "@action")
        method.__qgis_sdk_action__ = declared
        return method

    if method is None:
        return decorate
    return decorate(method)


@dataclass(frozen=True)
class _StreamMetadata(Metadata):
    events: dict[str, Any]


def stream(
    *, events: Any, id: str | None = None, title: str | None = None
) -> Callable[[T], T]:
    """Attach stream metadata to an instance method that produces events.

    ``events`` maps each event kind the stream emits (``data``, ``progress``,
    ``state``) to the annotation of that kind's payload. It is the declaration of
    the wire (decision-28): the method's parameters are the subscribe request,
    its return annotation is not described (it still has to resolve, like every
    annotation), and a kind the map does not name is one the host refuses to
    emit. An omitted ``id`` or ``title`` comes from the method name, as for
    ``@action``.
    """
    validate_given(id, title)
    label = id if id is not None else "stream"
    if not isinstance(events, dict):
        raise QgisSdkDeclarationError(
            f"{label}: events must be a mapping of kind to type"
        )
    if not events:
        raise QgisSdkDeclarationError(
            f"{label}: a stream declares at least one event kind"
        )
    for kind in events:
        if kind not in STREAM_EVENT_KINDS:
            raise QgisSdkDeclarationError(
                f"{label}: {kind!r} is not a stream event kind; "
                f"use one of {', '.join(STREAM_EVENT_KINDS)}"
            )

    def decorate(method: T) -> T:
        if not inspect.isfunction(method):
            raise QgisSdkDeclarationError("@stream requires an instance method")
        declared = method_metadata(method, id, title)
        _require_undeclared(method, declared.id, "@stream")
        refuse_bindings(method, "@stream")
        method.__qgis_sdk_stream__ = _StreamMetadata(
            declared.id, declared.title, dict(events)
        )
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


def object_schema(properties: dict, required: list[str]) -> dict[str, Any]:
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
    declared = getattr(annotation, WIRE_SCHEMA_ATTRIBUTE, None)
    if result and inspect.isclass(annotation) and isinstance(declared, dict):
        # An SDK value type that says how it crosses the wire (``JobHandle``):
        # a result only - a caller cannot send one in.
        return _json_copy(declared)
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
    return object_schema(properties, required)


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


def keyword_inputs(
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
