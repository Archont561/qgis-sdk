"""JSON Schema generation for inputs and results."""

from __future__ import annotations

import inspect
from dataclasses import MISSING, fields, is_dataclass
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin, get_type_hints

from qgis_sdk.declarations._contract import QgisSdkDeclarationError
from qgis_sdk.declarations._descriptions import _json_copy
from qgis_sdk.declarations._plugin import WIRE_SCHEMA_ATTRIBUTE
from qgis_sdk.models import MAX_SAFE_INTEGER
from qgis_sdk.models.files import FILE_REF, FileRef
from qgis_sdk.models.parameters import RangeParameter

from ._kinds import WIRE_KIND_KEYWORD, resolve_kind

__all__ = ["object_schema", "resolve_hints", "schema_for"]


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
        return _annotated_schema(annotation, path, result=result, stack=stack)
    primitive = _primitive_name(annotation)
    if primitive is not None:
        return _primitive_schema(annotation, primitive)
    return _composed_schema(annotation, path, result=result, stack=stack)


def _primitive_name(annotation: Any) -> str | None:
    """The JSON type a primitive annotation maps to, or ``None`` for the rest."""
    return next(
        (name for cls, name in _PRIMITIVE_JSON_TYPES.items() if annotation is cls),
        None,
    )


def _annotated_schema(
    annotation: Any, path: str, *, result: bool, stack: tuple
) -> dict[str, Any]:
    """Describe an ``Annotated``: an input carries intent, a result stores a value."""
    if result:
        return _schema(get_args(annotation)[0], path, result=True, stack=stack)
    return _input_schema(annotation, path, stack=stack)


def _composed_schema(
    annotation: Any, path: str, *, result: bool, stack: tuple
) -> dict[str, Any]:
    """Describe the composites, then what a value type declares, then refuse."""
    if annotation is FileRef and not result:
        raise QgisSdkDeclarationError(
            f"{path}: a FileRef input needs FileInput(filters=...) or "
            "DirectoryInput() to say which picker fills it"
        )
    generic = _generic_schema(annotation, path, result=result, stack=stack)
    if generic is not None:
        return generic
    declared = _declared_schema(annotation, path, result=result, stack=stack)
    if declared is not None:
        return declared
    raise QgisSdkDeclarationError(
        f"{path}: unsupported annotation {annotation!r}; use JSON primitives, "
        "list, tuple[X, ...], union, Literal or a dataclass"
    )


def _generic_schema(
    annotation: Any, path: str, *, result: bool, stack: tuple
) -> dict[str, Any] | None:
    """The parameterised annotations: unions, one-length lists, tuples, literals."""
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
    return None


def _declared_schema(
    annotation: Any, path: str, *, result: bool, stack: tuple
) -> dict[str, Any] | None:
    """The shape a value type declares for itself, or the one its fields imply.

    A declared shape wins over the generic walk: an SDK value type that says how
    it crosses the wire (``RunResult``, ``JobHandle``) describes itself better
    than its fields can.
    """
    declared = getattr(annotation, WIRE_SCHEMA_ATTRIBUTE, None)
    if result and isinstance(declared, dict):
        return _json_copy(declared)
    if inspect.isclass(annotation) and is_dataclass(annotation):
        return _dataclass_schema(annotation, path, result=result, stack=stack)
    return None


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
