"""JSON Schema generation for inputs and results, and the parameter-kind rules."""

import inspect
from dataclasses import MISSING, fields, is_dataclass
from types import UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from qgis_sdk.declarations._contract import QgisSdkDeclarationError
from qgis_sdk.declarations._descriptions import _json_copy
from qgis_sdk.declarations._plugin import WIRE_SCHEMA_ATTRIBUTE
from qgis_sdk.models import MAX_SAFE_INTEGER
from qgis_sdk.models.files import FILE_REF, FileRef
from qgis_sdk.models.parameters import ParameterKind, RangeParameter, parameter_kinds


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
        if result:
            # A result carries no intent for a host; describe what it stores.
            return _schema(get_args(annotation)[0], path, result=True, stack=stack)
        return _input_schema(annotation, path, stack=stack)
    if annotation is FileRef and not result:
        raise QgisSdkDeclarationError(
            f"{path}: a FileRef input needs FileInput(filters=...) or "
            "DirectoryInput() to say which picker fills it"
        )
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


WIRE_KIND_KEYWORD = "x-qgis-sdk"
"""The schema keyword an input's kind rides on, so a page draws the right widget."""

_ENUM_KIND = parameter_kinds()["enum"]
_PRIMITIVE_KIND_NAMES: dict[Any, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
}


def resolve_kind(
    path: str, annotation: Any, *, strict: bool = True
) -> tuple[ParameterKind, Any]:
    """Map one input annotation onto its :class:`ParameterKind` and marker.

    ``LayerInput`` and ``Annotated[str, LayerParameter()]`` are the same
    annotation, so they map to the same kind; a marker on a type it does not
    fit (``Annotated[int, LayerParameter()]``) is refused with ``path`` named.
    ``Literal[...]`` of strings is the ``enum`` kind; the marker is ``None``
    for it and for the primitives. An ``Annotated`` extra that is not an SDK
    marker is refused when ``strict`` (an algorithm's inputs all render in a
    toolbox) and skipped otherwise (an action may carry another library's
    metadata beside the SDK's).
    """
    kinds = parameter_kinds()
    base, markers = annotation, ()
    if get_origin(annotation) is Annotated:
        base, *markers = get_args(annotation)
    for marker in markers:
        kind = next((k for k in kinds.values() if k.marker is type(marker)), None)
        if kind is None:
            if strict:
                raise _refuse_kind(path, f"unknown parameter marker {marker!r}")
            continue
        if base not in kind.stored:
            raise _refuse_kind(path, kind.refusal)
        return kind, marker
    if get_origin(base) is Literal:
        choices = get_args(base)
        if not choices or not all(type(choice) is str for choice in choices):
            raise _refuse_kind(path, "enum choices must be strings")
        return _ENUM_KIND, None
    if base is FileRef:
        raise _refuse_kind(
            path, "a FileRef input needs FileInput(filters=...) or DirectoryInput()"
        )
    name = _PRIMITIVE_KIND_NAMES.get(base)
    if name is None:
        raise _refuse_kind(path, f"cannot express {base!r} as a host parameter")
    return kinds[name], None


def _refuse_kind(path: str, detail: str) -> QgisSdkDeclarationError:
    supported = ", ".join(parameter_kinds())
    return QgisSdkDeclarationError(
        f"{path}: {detail}; use Annotated markers ({supported})"
    )


def _input_schema(annotation: Any, path: str, *, stack: tuple) -> dict[str, Any]:
    """Describe an ``Annotated`` input: what it stores plus the kind it means.

    The stored type still decides the JSON shape, so the subset stays one
    dialect; the marker adds ``x-qgis-sdk`` (and, for a range, the standard
    bounds) so a page, a form or an agent reads the intent without the
    Python signature.
    """
    base = get_args(annotation)[0]
    if base is FileRef:
        kind, marker = resolve_kind(path, annotation, strict=False)
        schema = _json_copy(FILE_REF)
    else:
        schema = _schema(base, path, result=False, stack=stack)
        try:
            kind, marker = resolve_kind(path, annotation, strict=False)
        except QgisSdkDeclarationError as error:
            if "cannot express" not in str(error):
                raise
            # A shape the wire carries (a dataclass, a list) that no kind
            # names: described by its type, without a kind, as before.
            return schema
    if marker is None:
        return schema
    if isinstance(marker, RangeParameter):
        schema["minimum"] = marker.minimum
        schema["maximum"] = marker.maximum
    schema[WIRE_KIND_KEYWORD] = kind.annotation(marker)
    return schema


def check_field_parents(properties: dict[str, Any], path: str) -> None:
    """Refuse a field input whose ``of`` is not a layer input of the same call."""
    for name, schema in properties.items():
        intent = schema.get(WIRE_KIND_KEYWORD) if isinstance(schema, dict) else None
        if not intent or intent.get("kind") != "field":
            continue
        parent = properties.get(intent["of"])
        if parent is None:
            raise QgisSdkDeclarationError(
                f"{path}.{name}: of={intent['of']!r} names no input of this "
                "declaration; a field input belongs to a layer input"
            )
        parent_kind = (parent.get(WIRE_KIND_KEYWORD) or {}).get(
            "kind", parent.get("type")
        )
        if parent_kind != "layer":
            raise QgisSdkDeclarationError(
                f"{path}.{name}: of={intent['of']!r} names a {parent_kind} input; "
                "a field input belongs to a layer input"
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
    check_field_parents(properties, path)
    return properties, required
