"""Emission helpers: the call and open templates, trees, interfaces and validators."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from qgis_sdk.models.errors import QgisSdkBridgeError

from qgis_sdk_tools.generate._contract import (
    _SIMPLE_TYPES,
    KIND_KEYWORD,
    _Surface,
    is_open_map,
)
from qgis_sdk_tools.generate._names import Action, Stream


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_inline_validator_p1(_s):
    from ._validators import inline_validator

    if "anyOf" in _s.schema:
        return CcReturn(
            "("
            + " || ".join(
                inline_validator(branch, _s.expression, _s.generator)
                for branch in _s.schema["anyOf"]
            )
            + ")"
        )


def cc_inline_validator_p2(_s):
    from ._validators import literal

    if "enum" in _s.schema:
        return CcReturn(
            "("
            + " || ".join(
                f"{_s.expression} === {literal(value)}" for value in _s.schema["enum"]
            )
            + ")"
        )
    _s.declared = _s.schema.get("type")


def cc_inline_validator_p3(_s):
    from ._validators import VALIDATORS, inline_validator

    if isinstance(_s.declared, list):
        return CcReturn(
            "("
            + " || ".join(
                inline_validator({"type": alternative}, _s.expression, _s.generator)
                for alternative in _s.declared
            )
            + ")"
        )
    _s.validate = VALIDATORS.get(_s.declared) if isinstance(_s.declared, str) else None
    if _s.validate is None:
        raise QgisSdkBridgeError(f"cannot validate {_s.declared!r}")


def cc_inline_validator_p4(_s):
    return CcReturn(_s.validate(_s.schema, _s.expression, _s.generator))


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


class Namer(Protocol):
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
    from ._validators import quote

    lines: list[str] = []
    indent = "\t" * depth
    for key in sorted(tree):
        value = tree[key]
        if isinstance(value, dict):
            lines.append(f"{indent}readonly {quote(key)}: {{")
            lines.extend(_emit_tree(value, render, depth=depth + 1))
            lines.append(f"{indent}}};")
        else:
            lines.append(f"{indent}{render(value)}")
    return lines


def _emit_tree_body(tree: dict[str, Any], render: Any, *, depth: int) -> list[str]:
    from ._validators import quote

    lines: list[str] = []
    indent = "\t" * depth
    for key in sorted(tree):
        value = tree[key]
        if isinstance(value, dict):
            lines.append(f"{indent}{quote(key)}: {{")
            lines.extend(_emit_tree_body(value, render, depth=depth + 1))
            lines.append(f"{indent}}},")
        else:
            lines.append(f"{indent}{render(value)}")
    return lines


def interface_lines(
    schema: Mapping[str, Any], name: str, generator: Namer
) -> list[str]:
    from ._validators import quote

    required = set(schema.get("required", []) or [])
    properties: Mapping[str, Any] = schema.get("properties") or {}
    lines = [f"export interface {name} {{"]
    for key in sorted(properties):
        optional = "" if key in required else "?"
        intent = properties[key].get(KIND_KEYWORD)
        if isinstance(intent, Mapping) and isinstance(intent.get("kind"), str):
            lines.append(f"\t/** @qgis-sdk-kind {intent['kind']} */")
        lines.append(
            f"\treadonly {quote(str(key))}{optional}: "
            f"{_field_type(properties[key], generator)};"
        )
    if not properties:
        lines.append("\treadonly [key: string]: never;")
    lines.append("}")
    return lines


def validator_lines(
    schema: Mapping[str, Any], name: str, generator: Namer
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


def _field_type(schema: Mapping[str, Any], generator: Namer) -> str:
    """Name an object by its registered interface, and look inside an array."""
    from ._validators import inline_type

    name = generator.name_for(schema)
    if name is not None:
        return name
    if schema.get("type") == "array":
        return f"readonly {_element(_field_type(schema['items'], generator))}[]"
    return inline_type(schema, generator)


def _element(rendered: str) -> str:
    """Parenthesise a union so ``readonly (a | b)[]`` is the array it means."""
    return f"({rendered})" if " | " in rendered else rendered


def _member_validator(
    expression: str, schema: Mapping[str, Any], generator: Namer
) -> str:
    """Validate by name where the item has one, so a page item uses its interface."""
    from ._validators import inline_validator

    name = generator.name_for(schema)
    if name is not None:
        return f"{name}({expression}, strict)"
    if schema.get("type") == "array":
        inner = _member_validator("item", schema["items"], generator)
        return f"(Array.isArray({expression}) && {expression}.every((item) => {inner}))"
    return inline_validator(schema, expression, generator)


def _simple_type(schema: Mapping[str, Any], generator: Namer | None) -> str:
    """A JSON scalar maps straight to its TypeScript keyword."""
    return _SIMPLE_TYPES[schema["type"]]


def _array_type(schema: Mapping[str, Any], generator: Namer | None) -> str:
    """An array of unspecified values is a free-form payload, not a guess."""
    from ._validators import inline_type

    items = schema.get("items")
    if items is None:
        return "readonly unknown[]"
    return f"readonly {_element(inline_type(items, generator))}[]"


def _object_type(schema: Mapping[str, Any], generator: Namer | None) -> str:
    """A titled object is its own declaration; an untitled one is an open map."""
    if is_open_map(schema):
        return "Record<string, unknown>"
    named = None if generator is None else generator.name_for(schema)
    return named if named is not None else "Record<string, unknown>"


TYPE_RENDERERS: dict[Any, Callable[[Mapping[str, Any], Namer | None], str]] = {
    **{kind: _simple_type for kind in _SIMPLE_TYPES},
    "array": _array_type,
    "object": _object_type,
}
