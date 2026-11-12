from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.models.limits import MAX_SAFE_INTEGER

from qgis_sdk_tools.generate._contract import (
    _IDENTIFIER_SAFE,
    _KNOWN_KEYWORDS,
    is_open_map,
)

from ._validator_state import (
    TYPE_RENDERERS,
    CcReturn,
    CcState,
    Namer,
    cc_inline_validator_p1,
    cc_inline_validator_p2,
    cc_inline_validator_p3,
    cc_inline_validator_p4,
)


def inline_type(schema: Mapping[str, Any], generator: Namer | None = None) -> str:
    if "anyOf" in schema:
        return " | ".join(inline_type(branch, generator) for branch in schema["anyOf"])
    if "enum" in schema:
        return " | ".join(literal(value) for value in schema["enum"])
    declared = schema.get("type")
    if isinstance(declared, list):
        # ``"type": ["string", "number"]`` is a union the writer already spelled
        # out; rendering each alternative is the same thing spelled the long way.
        return " | ".join(
            inline_type({"type": alternative}, generator) for alternative in declared
        )
    render = TYPE_RENDERERS.get(declared)
    if render is None:
        raise QgisSdkBridgeError(f"cannot render a type for {declared!r}")
    return render(schema, generator)


def _validate_array(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    items = schema.get("items")
    if items is None:
        return f"Array.isArray({expression})"
    return (
        f"(Array.isArray({expression}) && {expression}.every((item) => "
        f"{inline_validator(items, 'item', generator)}))"
    )


def _validate_string(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    test = f'typeof {expression} === "string"'
    pattern = schema.get("pattern")
    if pattern is not None:
        test += f" && {_pattern_test(pattern, expression)}"
    return test


def _validate_boolean(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    return f'typeof {expression} === "boolean"'


def _validate_number(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    checks = [f'typeof {expression} === "number" && Number.isFinite({expression})']
    checks.extend(_bound_checks(schema, expression))
    if len(checks) == 1:
        return checks[0]
    return "(" + " && ".join(checks) + ")"


def _validate_integer(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    # The safe range is already `isSafeInteger`; a tighter bound the manifest
    # declared (a page size, say) is worth refusing before the transport,
    # because the host would refuse it anyway and the page could have known.
    checks = [f"isSafeInteger({expression})"]
    checks.extend(_bound_checks(schema, expression))
    if len(checks) == 1:
        return checks[0]
    return "(" + " && ".join(checks) + ")"


def _validate_null(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    return f"{expression} === null"


def _validate_object(
    schema: Mapping[str, Any], expression: str, generator: Namer | None
) -> str:
    if is_open_map(schema):
        return f"isRecord({expression})"
    named = None if generator is None else generator.name_for(schema)
    if named is not None:
        return f"{named}({expression}, strict)"
    return f"isRecord({expression})"


VALIDATORS: dict[str, Callable[[Mapping[str, Any], str, Namer | None], str]] = {
    "array": _validate_array,
    "string": _validate_string,
    "boolean": _validate_boolean,
    "number": _validate_number,
    "integer": _validate_integer,
    "null": _validate_null,
    "object": _validate_object,
}
"""How each declared JSON type is checked on the page."""


def inline_validator(
    schema: Mapping[str, Any], expression: str, generator: Namer | None = None
) -> str:
    _s = CcState(schema=schema, expression=expression, generator=generator)
    for _p in (
        cc_inline_validator_p1,
        cc_inline_validator_p2,
        cc_inline_validator_p3,
        cc_inline_validator_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


def _bound_checks(schema: Mapping[str, Any], expression: str) -> list[str]:
    """Render the declared ``minimum``/``maximum`` the host will enforce too."""
    checks: list[str] = []
    for keyword, operator in (("minimum", ">="), ("maximum", "<=")):
        bound = schema.get(keyword)
        if isinstance(bound, bool) or not isinstance(bound, int | float):
            continue
        if abs(bound) == MAX_SAFE_INTEGER:
            continue
        checks.append(f"{expression} {operator} {json.dumps(bound)}")
    return checks


def _pattern_test(pattern: Any, expression: str) -> str:
    """Test a whole string against a declared pattern, the way the host does.

    ``re.fullmatch`` on the host side and ``^(?:...)$`` here mean the same
    thing, so a manifest pattern never has to carry its own anchors.
    """
    if not isinstance(pattern, str):
        raise QgisSdkBridgeError("a string pattern must be a string")
    return f"new RegExp({json.dumps(f'^(?:{pattern})$')}).test({expression})"


def check_supported(schema: Any, *, path: str) -> None:
    if not isinstance(schema, Mapping):
        raise QgisSdkBridgeError(f"{path}: a schema must be an object")
    unknown = set(schema) - _KNOWN_KEYWORDS
    if unknown:
        raise QgisSdkBridgeError(
            f"{path}: unsupported schema keyword(s) {', '.join(sorted(unknown))}"
        )
    for key, item in (schema.get("properties") or {}).items():
        check_supported(item, path=f"{path}.{key}")
    if isinstance(schema.get("items"), Mapping):
        check_supported(schema["items"], path=f"{path}[]")
    for branch in schema.get("anyOf", []) or []:
        check_supported(branch, path=path)


def sorted_declaration(described: Mapping[str, Any]) -> dict[str, Any]:
    """Return the declaration with its actions and streams in id order.

    The embedded JSON is what ``QgisSdk`` validates against, so it is the
    declaration as given; only the order of the two lists is normalised so the
    module stays byte-identical whatever order a host enumerated them in.
    """
    ordered = dict(described)
    for key in ("actions", "streams"):
        if isinstance(ordered.get(key), list):
            ordered[key] = sorted(ordered[key], key=lambda item: str(item["id"]))
    return ordered


def json_lines(value: Mapping[str, Any]) -> list[str]:
    """Render the body of ``value`` as tab-indented JSON, braces left to the caller."""
    text = json.dumps(value, indent="\t", ensure_ascii=False, allow_nan=False)
    inner = text.splitlines()[1:-1]
    return list(inner)


def pascal(value: str) -> str:
    parts = [part for part in value.replace("-", ".").split(".") if part]
    name = "".join(part[:1].upper() + part[1:] for part in parts)
    if not name:
        raise QgisSdkBridgeError(f"cannot name a type for {value!r}")
    return name if name[0].isalpha() else f"Op{name}"


def quote(value: str) -> str:
    if (
        value
        and all(character in _IDENTIFIER_SAFE for character in value)
        and not value[0].isdigit()
    ):
        return value
    return json.dumps(value)


def literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)
