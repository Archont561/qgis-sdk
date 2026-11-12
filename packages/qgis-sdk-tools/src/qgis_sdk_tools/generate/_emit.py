"""Emission helpers: the call and open templates, trees, interfaces and validators."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.models.limits import MAX_SAFE_INTEGER

from qgis_sdk_tools.generate._contract import (
    _IDENTIFIER_SAFE,
    _KNOWN_KEYWORDS,
    _SIMPLE_TYPES,
    KIND_KEYWORD,
    _Surface,
    is_open_map,
)
from qgis_sdk_tools.generate._names import Action, Stream


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_inline_validator_p1(_s):
    if "anyOf" in _s.schema:
        return _CcReturn(
            "("
            + " || ".join(
                _inline_validator(branch, _s.expression, _s.generator)
                for branch in _s.schema["anyOf"]
            )
            + ")"
        )


def _cc_inline_validator_p2(_s):
    if "enum" in _s.schema:
        return _CcReturn(
            "("
            + " || ".join(
                f"{_s.expression} === {_literal(value)}" for value in _s.schema["enum"]
            )
            + ")"
        )
    _s.declared = _s.schema.get("type")


def _cc_inline_validator_p3(_s):
    if isinstance(_s.declared, list):
        return _CcReturn(
            "("
            + " || ".join(
                _inline_validator({"type": alternative}, _s.expression, _s.generator)
                for alternative in _s.declared
            )
            + ")"
        )
    _s.validate = _VALIDATORS.get(_s.declared) if isinstance(_s.declared, str) else None
    if _s.validate is None:
        raise QgisSdkBridgeError(f"cannot validate {_s.declared!r}")


def _cc_inline_validator_p4(_s):
    return _CcReturn(_s.validate(_s.schema, _s.expression, _s.generator))


_CC_TEXT_1 = """async function call<T>(
\tclient: BridgeClientLike,
\toperation: string,
\tinput: unknown,
\toptions: InvokeOptions | undefined,
\tacceptInput: (value: unknown, strict?: boolean) => boolean,
\tacceptOutput: (value: unknown) => boolean,
): Promise<T> {
\tif (input !== undefined && !acceptInput(input, true)) {
\t\tthrow new ContractError(operation, "the arguments do not match the declared request");
\t}
\tconst value = await client.invoke(
\t\toperation,
\t\t(input ?? {}) as Readonly<Record<string, unknown>>,
\t\toptions,
\t);
\tif (!acceptOutput(value)) {
\t\tthrow new ContractError(operation, "the response does not match the declared result");
\t}
\treturn value as T;
}
"""
_CC_TEXT_2 = """async function open<E extends { readonly kind: string }>(
\tclient: BridgeClientLike,
\toperation: string,
\tinput: unknown,
\thandlers: StreamHandlers<E>,
\toptions: InvokeOptions | undefined,
\tacceptInput: (value: unknown, strict?: boolean) => boolean,
\tacceptEvent: (value: unknown) => value is E,
): Promise<StreamHandle> {
\tif (!acceptInput(input, true)) {
\t\tthrow new ContractError(operation, "the arguments do not match the declared request");
\t}
\t// The typed stream ends exactly once, like the subscription under it: a
\t// contract violation ends it here, closes the subscription, and the
\t// `disposed` the client then reports is not delivered a second time.
\tlet ended = false;
\tlet violated = false;
\tlet handle: StreamHandle | null = null;
\tconst end = (terminal: StreamTerminal): void => {
\t\tif (ended) return;
\t\tended = true;
\t\thandlers.onTerminal?.(terminal);
\t};
\thandle = await client.subscribe(
\t\toperation,
\t\tinput as Readonly<Record<string, unknown>>,
\t\t{
\t\t\tonEvent: (event) => {
\t\t\t\tif (ended) return;
\t\t\t\tif (acceptEvent(event)) {
\t\t\t\t\thandlers.onEvent?.(event);
\t\t\t\t\treturn;
\t\t\t\t}
\t\t\t\tend({
\t\t\t\t\tkind: "error",
\t\t\t\t\tmessage: new ContractError(
\t\t\t\t\t\toperation,
\t\t\t\t\t\t"an event does not match the declared events",
\t\t\t\t\t).message,
\t\t\t\t});
\t\t\t\tif (handle === null) {
\t\t\t\t\tviolated = true;
\t\t\t\t} else {
\t\t\t\t\thandle.close();
\t\t\t\t}
\t\t\t},
\t\t\tonTerminal: end,
\t\t},
\t\toptions,
\t);
\tif (violated) {
\t\thandle.close();
\t}
\treturn handle;
}
"""


class _Namer(Protocol):
    """What emission asks of the generator: the name of a schema, if it has one."""

    def name_for(self, schema: Mapping[str, Any]) -> str | None:
        """Return the exported type name registered for ``schema``."""
        ...


_CALL_HELPER = _CC_TEXT_1


_OPEN_HELPER = _CC_TEXT_2


def call_helper(surface: _Surface) -> str:
    """Render the call helper with this surface's identifiers."""
    return _with_surface_names(_CALL_HELPER, surface)


def open_helper(surface: _Surface) -> str:
    """Render the stream helper with this surface's identifiers."""
    return _with_surface_names(_OPEN_HELPER, surface)


def _with_surface_names(template: str, surface: _Surface) -> str:
    """Rename the plugin-surface identifiers a template is written with.

    Whole identifiers only: ``StreamHandle`` must not be rewritten inside
    ``StreamHandlers``, and a name already prefixed must not be prefixed again.
    """
    for placeholder, name in (
        ("BridgeClientLike", surface.client_type),
        ("InvokeOptions", surface.options_type),
        ("ContractError", surface.error_type),
        ("StreamHandlers", surface.stream_handlers_type),
        ("StreamHandle", surface.stream_handle_type),
        ("StreamTerminal", surface.stream_terminal_type),
    ):
        template = re.sub(rf"\b{placeholder}\b", name, template)
    return template


def tree_lines(actions: tuple[Action | Stream, ...], render: Any) -> list[str]:
    """Render the nested interface, grouping ids by their leading segments."""
    tree = _group(actions)
    return _emit_tree(tree, render, depth=1)


def tree_body_lines(actions: tuple[Action | Stream, ...], render: Any) -> list[str]:
    tree = _group(actions)
    return _emit_tree_body(tree, render, depth=2)


def _group(actions: tuple[Action | Stream, ...]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for action in sorted(actions, key=lambda item: item.id):
        segments = action.id.split(".")
        node = root
        for segment in segments[:-1]:
            node = node.setdefault(segment, {})
            if not isinstance(node, dict):
                raise QgisSdkBridgeError(
                    f"{action.id}: conflicts with an action of the same prefix"
                )
        if segments[-1] in node and isinstance(node[segments[-1]], dict):
            raise QgisSdkBridgeError(
                f"{action.id}: conflicts with actions declared below it"
            )
        node[segments[-1]] = action
    return root


def _emit_tree(tree: dict[str, Any], render: Any, *, depth: int) -> list[str]:
    lines: list[str] = []
    indent = "\t" * depth
    for key in sorted(tree):
        value = tree[key]
        if isinstance(value, dict):
            lines.append(f"{indent}readonly {_quote(key)}: {{")
            lines.extend(_emit_tree(value, render, depth=depth + 1))
            lines.append(f"{indent}}};")
        else:
            lines.append(f"{indent}{render(value)}")
    return lines


def _emit_tree_body(tree: dict[str, Any], render: Any, *, depth: int) -> list[str]:
    lines: list[str] = []
    indent = "\t" * depth
    for key in sorted(tree):
        value = tree[key]
        if isinstance(value, dict):
            lines.append(f"{indent}{_quote(key)}: {{")
            lines.extend(_emit_tree_body(value, render, depth=depth + 1))
            lines.append(f"{indent}}},")
        else:
            lines.append(f"{indent}{render(value)}")
    return lines


def interface_lines(
    schema: Mapping[str, Any], name: str, generator: _Namer
) -> list[str]:
    required = set(schema.get("required", []) or [])
    properties: Mapping[str, Any] = schema.get("properties") or {}
    lines = [f"export interface {name} {{"]
    for key in sorted(properties):
        optional = "" if key in required else "?"
        intent = properties[key].get(KIND_KEYWORD)
        if isinstance(intent, Mapping) and isinstance(intent.get("kind"), str):
            lines.append(f"\t/** @qgis-sdk-kind {intent['kind']} */")
        lines.append(
            f"\treadonly {_quote(str(key))}{optional}: "
            f"{_field_type(properties[key], generator)};"
        )
    if not properties:
        lines.append("\treadonly [key: string]: never;")
    lines.append("}")
    return lines


def validator_lines(
    schema: Mapping[str, Any], name: str, generator: _Namer
) -> list[str]:
    required = list(schema.get("required", []) or [])
    properties: Mapping[str, Any] = schema.get("properties") or {}
    lines = [
        f"export function {name}(value: unknown, strict = false): value is {name} {{",
        "\tif (!isRecord(value)) return false;",
    ]
    for key in required:
        lines.append(f'\tif (!("{key}" in value)) return false;')
    for key in sorted(properties):
        expression = _member_validator(
            f"value[{json.dumps(str(key))}]", properties[key], generator
        )
        lines.append(
            f"\tif (value[{json.dumps(str(key))}] !== undefined && !({expression})) {{"
        )
        lines.append("\t\treturn false;")
        lines.append("\t}")
    known = ", ".join(json.dumps(str(key)) for key in sorted(properties))
    lines.append(f"\tif (strict && !hasOnly(value, [{known}])) return false;")
    lines.append("\treturn true;")
    lines.append("}")
    return lines


def _field_type(schema: Mapping[str, Any], generator: _Namer) -> str:
    """Name an object by its registered interface, and look inside an array."""
    name = generator.name_for(schema)
    if name is not None:
        return name
    if schema.get("type") == "array":
        return f"readonly {_element(_field_type(schema['items'], generator))}[]"
    return _inline_type(schema, generator)


def _element(rendered: str) -> str:
    """Parenthesise a union so ``readonly (a | b)[]`` is the array it means."""
    return f"({rendered})" if " | " in rendered else rendered


def _member_validator(
    expression: str, schema: Mapping[str, Any], generator: _Namer
) -> str:
    """Validate by name where the item has one, so a page item uses its interface."""
    name = generator.name_for(schema)
    if name is not None:
        return f"{name}({expression}, strict)"
    if schema.get("type") == "array":
        inner = _member_validator("item", schema["items"], generator)
        return f"(Array.isArray({expression}) && {expression}.every((item) => {inner}))"
    return _inline_validator(schema, expression, generator)


def _simple_type(schema: Mapping[str, Any], generator: _Namer | None) -> str:
    """A JSON scalar maps straight to its TypeScript keyword."""
    return _SIMPLE_TYPES[schema["type"]]


def _array_type(schema: Mapping[str, Any], generator: _Namer | None) -> str:
    """An array of unspecified values is a free-form payload, not a guess."""
    items = schema.get("items")
    if items is None:
        return "readonly unknown[]"
    return f"readonly {_element(_inline_type(items, generator))}[]"


def _object_type(schema: Mapping[str, Any], generator: _Namer | None) -> str:
    """A titled object is its own declaration; an untitled one is an open map."""
    if is_open_map(schema):
        return "Record<string, unknown>"
    named = None if generator is None else generator.name_for(schema)
    return named if named is not None else "Record<string, unknown>"


_TYPE_RENDERERS: dict[Any, Callable[[Mapping[str, Any], _Namer | None], str]] = {
    **{kind: _simple_type for kind in _SIMPLE_TYPES},
    "array": _array_type,
    "object": _object_type,
}


def _inline_type(schema: Mapping[str, Any], generator: _Namer | None = None) -> str:
    if "anyOf" in schema:
        return " | ".join(_inline_type(branch, generator) for branch in schema["anyOf"])
    if "enum" in schema:
        return " | ".join(_literal(value) for value in schema["enum"])
    declared = schema.get("type")
    if isinstance(declared, list):
        # ``"type": ["string", "number"]`` is a union the writer already spelled
        # out; rendering each alternative is the same thing spelled the long way.
        return " | ".join(
            _inline_type({"type": alternative}, generator) for alternative in declared
        )
    render = _TYPE_RENDERERS.get(declared)
    if render is None:
        raise QgisSdkBridgeError(f"cannot render a type for {declared!r}")
    return render(schema, generator)


def _validate_array(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
) -> str:
    items = schema.get("items")
    if items is None:
        return f"Array.isArray({expression})"
    return (
        f"(Array.isArray({expression}) && {expression}.every((item) => "
        f"{_inline_validator(items, 'item', generator)}))"
    )


def _validate_string(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
) -> str:
    test = f'typeof {expression} === "string"'
    pattern = schema.get("pattern")
    if pattern is not None:
        test += f" && {_pattern_test(pattern, expression)}"
    return test


def _validate_boolean(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
) -> str:
    return f'typeof {expression} === "boolean"'


def _validate_number(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
) -> str:
    checks = [f'typeof {expression} === "number" && Number.isFinite({expression})']
    checks.extend(_bound_checks(schema, expression))
    if len(checks) == 1:
        return checks[0]
    return "(" + " && ".join(checks) + ")"


def _validate_integer(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
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
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
) -> str:
    return f"{expression} === null"


def _validate_object(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None
) -> str:
    if is_open_map(schema):
        return f"isRecord({expression})"
    named = None if generator is None else generator.name_for(schema)
    if named is not None:
        return f"{named}({expression}, strict)"
    return f"isRecord({expression})"


_VALIDATORS: dict[str, Callable[[Mapping[str, Any], str, _Namer | None], str]] = {
    "array": _validate_array,
    "string": _validate_string,
    "boolean": _validate_boolean,
    "number": _validate_number,
    "integer": _validate_integer,
    "null": _validate_null,
    "object": _validate_object,
}
"""How each declared JSON type is checked on the page."""


def _inline_validator(
    schema: Mapping[str, Any], expression: str, generator: _Namer | None = None
) -> str:
    _s = _CcState(schema=schema, expression=expression, generator=generator)
    for _p in (
        _cc_inline_validator_p1,
        _cc_inline_validator_p2,
        _cc_inline_validator_p3,
        _cc_inline_validator_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
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


def _check_supported(schema: Any, *, path: str) -> None:
    if not isinstance(schema, Mapping):
        raise QgisSdkBridgeError(f"{path}: a schema must be an object")
    unknown = set(schema) - _KNOWN_KEYWORDS
    if unknown:
        raise QgisSdkBridgeError(
            f"{path}: unsupported schema keyword(s) {', '.join(sorted(unknown))}"
        )
    for key, item in (schema.get("properties") or {}).items():
        _check_supported(item, path=f"{path}.{key}")
    if isinstance(schema.get("items"), Mapping):
        _check_supported(schema["items"], path=f"{path}[]")
    for branch in schema.get("anyOf", []) or []:
        _check_supported(branch, path=path)


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


def _quote(value: str) -> str:
    if (
        value
        and all(character in _IDENTIFIER_SAFE for character in value)
        and not value[0].isdigit()
    ):
        return value
    return json.dumps(value)


def _literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)
