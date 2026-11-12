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
import re
from collections.abc import Mapping
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_check_p1(_s):
    if not isinstance(_s.schema, Mapping):
        raise QgisSdkBridgeError(f"{_s.path}: a schema must be an object")
    _s.unknown = set(_s.schema) - _KNOWN_KEYWORDS
    if _s.unknown:
        raise QgisSdkBridgeError(
            f"{_s.path}: unsupported schema keyword(s) {', '.join(sorted(_s.unknown))}"
        )


def _cc_check_p2(_s):
    if "anyOf" in _s.schema:
        _s.branches = _s.schema["anyOf"]
        if not isinstance(_s.branches, list) or not _s.branches:
            raise QgisSdkBridgeError(f"{_s.path}: anyOf must be a nonempty list")
        _s.failures = []
        for branch in _s.branches:
            _s.branch = branch
            try:
                _check(
                    _s.value, _s.branch, path=_s.path, allow_unknown=_s.allow_unknown
                )
            except QgisSdkBridgeError as error:
                _s.error = error
                _s.failures.append(str(_s.error))
            else:
                return _CcReturn(None)
        raise QgisSdkBridgeError(
            f"{_s.path}: matches none of the allowed forms ({'; '.join(_s.failures)})"
        )


def _cc_check_p3(_s):
    # ``"type": ["string", "number"]`` says what ``anyOf`` says the long way;
    # an expression's value is the case that needs it.
    _s.failures = []


def _cc_check_p4(_s):
    for alternative in _s.declared:
        _s.alternative = alternative
        try:
            _check(
                _s.value,
                {key: item for key, item in _s.schema.items() if key != "type"}
                | {"type": _s.alternative},
                path=_s.path,
                allow_unknown=_s.allow_unknown,
            )
        except QgisSdkBridgeError as error:
            _s.error = error
            _s.failures.append(str(_s.error))
        else:
            return _CcReturn(None)


def _cc_check_p5(_s):
    raise QgisSdkBridgeError(
        f"{_s.path}: matches none of the allowed types ({'; '.join(_s.failures)})"
    )


def _cc_check_p6(_s):
    if "enum" in _s.schema:
        _check_enum(_s.value, _s.schema["enum"], path=_s.path)
        return _CcReturn(None)
    _s.declared = _s.schema.get("type")
    if _s.declared is None:
        raise QgisSdkBridgeError(f"{_s.path}: a schema needs a type, anyOf or enum")
    if isinstance(_s.declared, list):
        for _p in (_cc_check_p3, _cc_check_p4, _cc_check_p5):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r


def _cc_check_p7(_s):
    if _s.declared not in _PRIMITIVES:
        raise QgisSdkBridgeError(f"{_s.path}: unsupported type {_s.declared!r}")
    _s.checker = _CHECKERS[_s.declared]
    _s.checker(_s.value, _s.schema, path=_s.path, allow_unknown=_s.allow_unknown)


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
        "pattern",
        "title",
        "description",
        # The input kind a describer annotated; read by forms and pages,
        # never by validation (``qgis_sdk.declarations.WIRE_KIND_KEYWORD``).
        "x-qgis-sdk",
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
    _s = _CcState(value=value, schema=schema, path=path, allow_unknown=allow_unknown)
    for _p in (_cc_check_p1, _cc_check_p2, _cc_check_p6, _cc_check_p7):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def _check_string(
    value: Any, schema: Mapping, *, path: str, allow_unknown: bool
) -> None:
    if not isinstance(value, str):
        raise QgisSdkBridgeError(f"{path}: expected a string, got {_name(value)}")
    pattern = schema.get("pattern")
    if pattern is None:
        return
    if not isinstance(pattern, str):
        raise QgisSdkBridgeError(f"{path}: pattern must be a string")
    try:
        matched = re.fullmatch(pattern, value)
    except re.error as error:
        raise QgisSdkBridgeError(
            f"{path}: pattern {pattern!r} is unusable: {error}"
        ) from error
    if matched is None:
        raise QgisSdkBridgeError(
            f"{path}: {value!r} does not match the declared pattern {pattern!r}"
        )


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


#: The Python types a payload may carry, in the order they are tested: ``bool``
#: before ``int`` because Python's ``True`` is one, and ``Mapping`` last because
#: everything else is checked first.
_TYPE_NAMES = (
    (bool, "boolean"),
    (str, "string"),
    (int, "integer"),
    (float, "number"),
    ((list, tuple), "array"),
    (Mapping, "object"),
)


def _name(value: Any) -> str:
    """Name a value's type the way a validation message says it."""
    if value is None:
        return "null"
    for kind, name in _TYPE_NAMES:
        if isinstance(value, kind):
            return name
    return type(value).__name__


__all__ = ["validate"]
