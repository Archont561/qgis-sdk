"""Validate a value against the schema subset the declarations already emit.

The bridge does not invent a second schema dialect and does not depend on a
validator package: ``qgis_sdk.declarations`` produces a small, closed subset
(objects with ``properties``/``required``/``additionalProperties``, arrays with
``items``, the five JSON primitives, ``anyOf`` and ``enum``, plus the integer
bounds), and this module checks exactly that. Anything outside it is refused
loudly, because a contract that silently accepts what it cannot check is not a
contract.

Two asymmetries are deliberate (decision-22, decision-26):

* **Inputs are strict.** Unknown properties are refused when the schema says
  ``additionalProperties: false`` - which is what the declaration generator
  always emits - so a misspelled argument never reaches Python.
* **Results are lenient.** ``allow_unknown=True`` ignores properties the schema
  does not mention, so a host may add fields without breaking an older client,
  while a missing or mistyped required field is still refused.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError

_PRIMITIVES = ("string", "boolean", "integer", "number", "null", "array", "object")
_KNOWN_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "enum",
        "minimum",
        "maximum",
        "title",
        "description",
    }
)


def validate(
    value: Any, schema: Mapping[str, Any], *, path: str, allow_unknown: bool = False
) -> None:
    """Refuse ``value`` unless it matches ``schema``; raise with the field path.

    ``path`` is where the value sits in the message (``payload.limit``), so a
    refusal names the argument a frontend author has to fix rather than saying
    "invalid payload".
    """
    _check(value, schema, path=path, allow_unknown=allow_unknown)


def _check(value: Any, schema: Any, *, path: str, allow_unknown: bool) -> None:
    if not isinstance(schema, Mapping):
        raise QgisSdkBridgeError(f"{path}: a schema must be an object")
    unknown = set(schema) - _KNOWN_KEYWORDS
    if unknown:
        raise QgisSdkBridgeError(
            f"{path}: unsupported schema keyword(s) {', '.join(sorted(unknown))}"
        )
    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not isinstance(branches, list) or not branches:
            raise QgisSdkBridgeError(f"{path}: anyOf must be a nonempty list")
        failures = []
        for branch in branches:
            try:
                _check(value, branch, path=path, allow_unknown=allow_unknown)
            except QgisSdkBridgeError as error:
                failures.append(str(error))
            else:
                return
        raise QgisSdkBridgeError(
            f"{path}: matches none of the allowed forms ({'; '.join(failures)})"
        )
    if "enum" in schema:
        _check_enum(value, schema["enum"], path=path)
        return
    declared = schema.get("type")
    if declared is None:
        raise QgisSdkBridgeError(f"{path}: a schema needs a type, anyOf or enum")
    if declared not in _PRIMITIVES:
        raise QgisSdkBridgeError(f"{path}: unsupported type {declared!r}")
    checker = _CHECKERS[declared]
    checker(value, schema, path=path, allow_unknown=allow_unknown)


def _check_string(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    if not isinstance(value, str):
        raise QgisSdkBridgeError(f"{path}: expected a string, got {_name(value)}")


def _check_boolean(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    if not isinstance(value, bool):
        raise QgisSdkBridgeError(f"{path}: expected a boolean, got {_name(value)}")


def _check_integer(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    # ``True`` is an ``int`` in Python and not an integer in JSON.
    if isinstance(value, bool) or not isinstance(value, int):
        raise QgisSdkBridgeError(f"{path}: expected an integer, got {_name(value)}")
    _check_bounds(value, schema, path=path)


def _check_number(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QgisSdkBridgeError(f"{path}: expected a number, got {_name(value)}")
    if isinstance(value, float) and not math.isfinite(value):
        raise QgisSdkBridgeError(f"{path}: expected a finite number")
    _check_bounds(value, schema, path=path)


def _check_null(value: Any, schema: Mapping, *, path: str, allow_unknown: bool) -> None:
    if value is not None:
        raise QgisSdkBridgeError(f"{path}: expected null, got {_name(value)}")


def _check_array(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    if not isinstance(value, (list, tuple)):
        raise QgisSdkBridgeError(f"{path}: expected an array, got {_name(value)}")
    items = schema.get("items")
    if items is None:
        return
    for index, item in enumerate(value):
        _check(item, items, path=f"{path}[{index}]", allow_unknown=allow_unknown)


def _check_object(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    if not isinstance(value, Mapping):
        raise QgisSdkBridgeError(f"{path}: expected an object, got {_name(value)}")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise QgisSdkBridgeError(f"{path}: properties must be an object")
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise QgisSdkBridgeError(f"{path}: required must be a list")
    for key in required:
        if key not in value:
            raise QgisSdkBridgeError(f"{path}.{key}: required property is missing")
    strict = schema.get("additionalProperties", True) is False and not allow_unknown
    for key, item in value.items():
        if not isinstance(key, str):
            raise QgisSdkBridgeError(f"{path}: property names must be strings")
        if key in properties:
            _check(
                item, properties[key], path=f"{path}.{key}", allow_unknown=allow_unknown
            )
        elif strict:
            raise QgisSdkBridgeError(f"{path}.{key}: unknown property")


_CHECKERS = {
    "string": _check_string,
    "boolean": _check_boolean,
    "integer": _check_integer,
    "number": _check_number,
    "null": _check_null,
    "array": _check_array,
    "object": _check_object,
}


def _check_enum(value: Any, choices: Any, *, path: str) -> None:
    if not isinstance(choices, list):
        raise QgisSdkBridgeError(f"{path}: enum must be a list")
    for choice in choices:
        # JSON equality is type-aware: ``true`` is not ``1``, and neither is
        # there an implicit ``"1"`` == ``1``.
        if type(choice) is type(value) and choice == value:
            return
    rendered = ", ".join(repr(choice) for choice in choices)
    raise QgisSdkBridgeError(f"{path}: expected one of {rendered}")


def _check_bounds(value: float, schema: Mapping, *, path: str) -> None:
    minimum, maximum = schema.get("minimum"), schema.get("maximum")
    if minimum is not None and value < minimum:
        raise QgisSdkBridgeError(f"{path}: {value} is below the minimum {minimum}")
    if maximum is not None and value > maximum:
        raise QgisSdkBridgeError(f"{path}: {value} is above the maximum {maximum}")


def _name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


__all__ = ["validate"]
