"""The generator: collect the schema pieces, then render them in a fixed order."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError

from qgis_sdk_tools.generate._contract import (
    _EVENT_KINDS,
    _TERMINAL_KINDS,
    CONTRACT_ERROR_CODE,
    GENERATED_MARKER,
    PLUGIN_SURFACE,
    _is_open_map,
    _shape,
    _Surface,
    contract_fingerprint,
)
from qgis_sdk_tools.generate._emit import (
    _call_helper,
    _check_supported,
    _inline_type,
    _inline_validator,
    _interface_lines,
    _json_lines,
    _member_validator,
    _open_helper,
    _pascal,
    _quote,
    _sorted_declaration,
    _tree_body_lines,
    _tree_lines,
    _validator_lines,
)
from qgis_sdk_tools.generate._names import (
    _Action,
    _check_sdk_tree,
    _declared_name,
    _Stream,
)


class _Generator:
    """Collect the schema pieces, then render them in a fixed order."""

    def __init__(
        self, description: Mapping[str, Any], *, surface: _Surface = PLUGIN_SURFACE
    ) -> None:
        self._description = description
        self._surface = surface
        self._objects: list[tuple[str, Mapping[str, Any]]] = []
        self._names: dict[int, str] = {}
        self._ids: set[str] = set()
        self._actions = self._collect_actions()
        self._streams = self._collect_streams()

    # -- collection ----------------------------------------------------

    def _claim(self, operation_id: str) -> None:
        """Hold actions and streams to one id namespace (decision-28)."""
        if operation_id in self._ids:
            raise QgisSdkBridgeError(f"duplicate operation id {operation_id!r}")
        self._ids.add(operation_id)

    def _collect_actions(self) -> tuple[_Action, ...]:
        actions: list[_Action] = []
        for raw in sorted(
            self._description["actions"], key=lambda item: str(item["id"])
        ):
            action_id = str(raw["id"])
            self._claim(action_id)
            request = raw.get("request")
            result = raw.get("result")
            if "events" in raw:
                raise QgisSdkBridgeError(
                    f"{action_id}: an action answers with a result; a stream "
                    "declares events and belongs in description.streams"
                )
            if not isinstance(request, Mapping) or not isinstance(result, Mapping):
                raise QgisSdkBridgeError(
                    f"{action_id}: the generator needs declared request and result schemas"
                )
            base = _pascal(action_id)
            request_name = raw.get("request_name")
            result_name = raw.get("result_name")
            actions.append(
                _Action(
                    id=action_id,
                    base=base,
                    request=request,
                    result=result,
                    takes_input=bool(request.get("required")),
                    request_name=request_name
                    if isinstance(request_name, str)
                    else None,
                    result_name=result_name if isinstance(result_name, str) else None,
                )
            )
            self._declare(
                request,
                _declared_name(
                    request_name, f"{base}Request", kind="request", action=action_id
                ),
            )
            self._declare(
                result,
                _declared_name(
                    result_name, f"{base}Result", kind="result", action=action_id
                ),
            )
        return tuple(actions)

    def _collect_streams(self) -> tuple[_Stream, ...]:
        streams: list[_Stream] = []
        for raw in sorted(
            self._description.get("streams") or [], key=lambda item: str(item["id"])
        ):
            stream_id = str(raw["id"])
            self._claim(stream_id)
            request = raw.get("request")
            events = raw.get("events")
            if "result" in raw:
                raise QgisSdkBridgeError(
                    f"{stream_id}: a stream declares events, not a result"
                )
            if not isinstance(request, Mapping) or not isinstance(events, Mapping):
                raise QgisSdkBridgeError(
                    f"{stream_id}: the generator needs a declared request schema "
                    "and an events map"
                )
            if not events:
                raise QgisSdkBridgeError(
                    f"{stream_id}: a stream declares at least one event kind"
                )
            unknown = sorted(str(kind) for kind in events if kind not in _EVENT_KINDS)
            if unknown:
                raise QgisSdkBridgeError(
                    f"{stream_id}: {', '.join(unknown)} is not a stream event kind; "
                    f"the frame carries {', '.join(_EVENT_KINDS)}"
                )
            base = _pascal(stream_id)
            request_name = raw.get("request_name")
            declared_events = tuple(
                (kind, events[kind]) for kind in _EVENT_KINDS if kind in events
            )
            for kind, schema in declared_events:
                if not isinstance(schema, Mapping):
                    raise QgisSdkBridgeError(
                        f"{stream_id}: events.{kind} must be a schema object"
                    )
            stream = _Stream(
                id=stream_id,
                base=base,
                request=request,
                events=declared_events,
                request_name=request_name if isinstance(request_name, str) else None,
            )
            self._declare(
                request,
                _declared_name(
                    request_name, f"{base}Request", kind="request", action=stream_id
                ),
            )
            for kind, schema in declared_events:
                self._declare(schema, f"{base}{_pascal(kind)}")
            streams.append(stream)
        return tuple(streams)

    def _declare(self, schema: Mapping[str, Any], name: str) -> str:
        """Name every object below ``schema`` before anything is rendered.

        Naming has to finish first: a parent's field type is the child's name, so
        rendering as we descend would point the parent at a name not yet chosen.
        """
        _check_supported(schema, path=name)
        self._register(schema, name)
        return name

    def _register(self, schema: Mapping[str, Any], name: str) -> None:
        if schema.get("type") == "object" and not _is_open_map(schema):
            if id(schema) in self._names:
                return
            if "title" in schema:
                # A titled object is exported under its own name wherever it
                # appears: a branded reference reads as ``FileRef``, not as the
                # field path it happened to be declared under first.
                name = _declared_name(schema["title"], name, kind="title", action=name)
            twin = next(
                (item for existing, item in self._objects if existing == name), None
            )
            if twin is not None:
                if _shape(twin) != _shape(schema):
                    raise QgisSdkBridgeError(
                        f"{name}: two declarations would generate the same type name; "
                        "rename one of the actions"
                    )
                # The same branded object declared twice (two file inputs are
                # both ``FileRef``): one exported type, both sites point at it.
                self._names[id(schema)] = name
                return
            self._names[id(schema)] = name
            self._objects.append((name, schema))
        for key, item in (schema.get("properties") or {}).items():
            self._register(item, f"{name}{_pascal(str(key))}")
        if isinstance(schema.get("items"), Mapping):
            self._register(schema["items"], f"{name}Item")
        for branch in schema.get("anyOf", []) or []:
            if branch.get("type") == "object":
                raise QgisSdkBridgeError(
                    f"{name}: an object inside a union has no generated type yet; "
                    "declare it as its own dataclass instead"
                )

    def name_for(self, schema: Mapping[str, Any]) -> str | None:
        """Return the registered name of an object schema, if it has one."""
        return self._names.get(id(schema))

    # -- rendering -----------------------------------------------------

    def _error_class_lines(self) -> list[str]:
        """Render the contract error: a plain ``Error`` with the wire code for a
        plugin module, a ``QgisSdkError`` subclass for the host module."""
        surface = self._surface
        head = [
            "/** An argument or a response that does not match its declared schema. */",
            f"export class {surface.error_type} extends {surface.error_base} {{",
        ]
        if surface.error_base == "Error":
            body = [
                f'\tpublic readonly code = "{CONTRACT_ERROR_CODE}";',
                "\tpublic readonly operation: string;",
                "\tpublic constructor(operation: string, message: string) {",
                '\t\tsuper(`operation "${operation}": ${message}`);',
                f'\t\tthis.name = "{surface.error_type}";',
                "\t\tthis.operation = operation;",
                "\t}",
            ]
        else:
            body = [
                "\tpublic readonly operation: string;",
                "\tpublic constructor(operation: string, message: string) {",
                (
                    '\t\tsuper(`operation "${operation}": ${message}`, '
                    f'"{CONTRACT_ERROR_CODE}");'
                ),
                "\t\tthis.operation = operation;",
                "\t}",
            ]
        return [*head, *body, "}"]

    def render(self) -> str:
        described = self._description
        surface = self._surface
        lines = [
            GENERATED_MARKER,
            *(
                line.format(id=described.get("id", "unknown plugin"))
                for line in surface.header
            ),
            *(line for line in ("", *surface.imports) if surface.imports),
            "",
            f'export const {surface.id_const} = "{described.get("id", "")}";',
            (
                f"export const {surface.fingerprint_const} = "
                f'"{contract_fingerprint(described)}";'
            ),
            (
                f"export const {surface.version_const} = "
                f"{int(described.get('schema_version', 1))};"
            ),
            "",
            "/** Every declared operation id, so a name can be checked, not guessed. */",
            f"export const {surface.operations_const} = [",
            *(f'\t"{operation}",' for operation in sorted(self._ids)),
            "] as const;",
            "",
            (
                f"export type {surface.operation_id_type} = "
                f"(typeof {surface.operations_const})[number];"
            ),
            "",
            f"export interface {surface.options_type} {{",
            "\treadonly signal?: AbortSignal;",
            "}",
            "",
            "/** The client this module wraps: anything with a correlated invoke. */",
            f"export interface {surface.client_type} {{",
            "\tinvoke(",
            "\t\toperation: string,",
            "\t\tpayload?: Readonly<Record<string, unknown>>,",
            f"\t\toptions?: {surface.options_type},",
            "\t): Promise<unknown>;",
            *self._subscribe_lines(),
            "}",
            "",
            *self._stream_support_lines(),
            *self._error_class_lines(),
            "",
            "function isRecord(value: unknown): value is Record<string, unknown> {",
            '\treturn typeof value === "object" && value !== null && !Array.isArray(value);',
            "}",
            "",
            "function hasOnly(",
            "\tvalue: Record<string, unknown>,",
            "\tkeys: readonly string[],",
            "): boolean {",
            "\treturn Object.keys(value).every((key) => keys.includes(key));",
            "}",
            "",
            "function isSafeInteger(value: unknown): value is number {",
            '\treturn typeof value === "number" && Number.isSafeInteger(value);',
            "}",
            "",
        ]
        for name, schema in sorted(self._objects):
            lines.extend(_interface_lines(schema, name, self))
            lines.append("")
        for name, schema in sorted(self._objects):
            lines.extend(_validator_lines(schema, name, self))
            lines.append("")
        for stream in self._streams:
            lines.extend(self._event_lines(stream))
            lines.append("")
        lines.extend(self._render_operations())
        return "\n".join(lines).rstrip("\n") + "\n"

    def render_schema(self, *, sdk_import: str) -> str:
        """Render the schema module: types plus the declaration, no code."""
        described = self._description
        _check_sdk_tree(self._ids)
        plugin_id = described.get("id", "")
        lines = [
            GENERATED_MARKER,
            *(
                line.format(id=described.get("id", "unknown plugin"))
                for line in PLUGIN_SURFACE.header
            ),
            "",
            (
                "import { type BridgeSchema, defineBridgeSchema } "
                f"from {json.dumps(sdk_import)};"
            ),
            "",
            f"export const PLUGIN_ID = {json.dumps(plugin_id)};",
            f'export const CONTRACT_FINGERPRINT = "{contract_fingerprint(described)}";',
            (
                "export const PLUGIN_DESCRIPTION_SCHEMA_VERSION = "
                f"{int(described.get('schema_version', 1))};"
            ),
            "",
            "/** Every declared operation id, so a name can be checked, not guessed. */",
            "export const OPERATIONS = [",
            *(f'\t"{operation}",' for operation in sorted(self._ids)),
            "] as const;",
            "",
            "export type OperationId = (typeof OPERATIONS)[number];",
            "",
        ]
        for name, schema in sorted(self._objects):
            lines.extend(_interface_lines(schema, name, self))
            lines.append("")
        for stream in self._streams:
            lines.extend(self._event_union_lines(stream))
            lines.append("")
        lines.extend(self._schema_map_lines())
        lines.extend(
            [
                "/** The declaration `describe_plugin` emitted, carrying the types above. */",
                (
                    "const schema: BridgeSchema<Operations, Streams> = "
                    "defineBridgeSchema<Operations, Streams>({"
                ),
                *_json_lines(_sorted_declaration(described)),
                "});",
                "",
                "export default schema;",
            ]
        )
        return "\n".join(lines).rstrip("\n") + "\n"

    def _event_union_lines(self, stream: _Stream) -> list[str]:
        """Render the event union of one stream, without a predicate."""
        lines = [
            f"/** One event of `{stream.id}`, narrowed by its kind. */",
            f"export type {stream.event_type} =",
        ]
        for kind, schema in stream.events:
            payload = self._type_name(schema, f"{stream.base}{_pascal(kind)}")
            lines.append(
                f"\t| {{ readonly kind: {json.dumps(kind)}; readonly payload: {payload} }}"
            )
        lines[-1] += ";"
        return lines

    def _schema_map_lines(self) -> list[str]:
        """Render ``Operations`` and ``Streams``, keyed by the full operation id."""
        lines = [
            "/** The declared actions by id: what goes in and what comes back. */",
        ]
        if self._actions:
            lines.append("export interface Operations {")
            for action in self._actions:
                request = self._type_name(action.request, f"{action.base}Request")
                result = self._type_name(action.result, f"{action.base}Result")
                lines.append(
                    f"\treadonly {_quote(action.id)}: {{ readonly request: {request}; "
                    f"readonly result: {result} }};"
                )
            lines.append("}")
        else:
            lines.append("export type Operations = Record<never, never>;")
        lines.append("")
        lines.append(
            "/** The declared streams by id: what goes in and the events that come out. */"
        )
        if self._streams:
            lines.append("export interface Streams {")
            for stream in self._streams:
                request = self._type_name(stream.request, f"{stream.base}Request")
                lines.append(
                    f"\treadonly {_quote(stream.id)}: {{ readonly request: {request}; "
                    f"readonly event: {stream.event_type} }};"
                )
            lines.append("}")
        else:
            lines.append("export type Streams = Record<never, never>;")
        lines.append("")
        return lines

    def _subscribe_lines(self) -> list[str]:
        """Require ``subscribe`` of the client only when a stream needs it."""
        if not self._streams:
            return []
        surface = self._surface
        kinds = " | ".join(json.dumps(kind) for kind in _EVENT_KINDS)
        return [
            "\tsubscribe(",
            "\t\toperation: string,",
            "\t\tpayload?: Readonly<Record<string, unknown>>,",
            f"\t\thandlers?: {surface.stream_handlers_type}<{{",
            f"\t\t\treadonly kind: {kinds};",
            "\t\t\treadonly payload: unknown;",
            "\t\t}>,",
            f"\t\toptions?: {surface.options_type},",
            f"\t): Promise<{surface.stream_handle_type}>;",
        ]

    def _stream_support_lines(self) -> list[str]:
        """The handler, handle and end types every stream member shares."""
        if not self._streams:
            return []
        surface = self._surface
        kinds = " | ".join(json.dumps(kind) for kind in _TERMINAL_KINDS)
        return [
            "/** How a stream ended; `dropped` is only present for a gap. */",
            f"export interface {surface.stream_terminal_type} {{",
            f"\treadonly kind: {kinds};",
            "\treadonly message?: string;",
            "\treadonly dropped?: number;",
            "}",
            "",
            "/** What a stream reports: typed events, then exactly one end. */",
            f"export interface {surface.stream_handlers_type}<E> {{",
            "\treadonly onEvent?: (event: E) => void;",
            f"\treadonly onTerminal?: (terminal: {surface.stream_terminal_type}) => void;",
            "}",
            "",
            "/** A live stream, as the caller holds it. */",
            f"export interface {surface.stream_handle_type} {{",
            "\treadonly id: string;",
            "\treadonly closed: boolean;",
            "\tclose(): void;",
            "}",
            "",
        ]

    def _event_lines(self, stream: _Stream) -> list[str]:
        """Render the event union of one stream and the predicate that narrows it."""
        name = stream.event_type
        lines = [
            f"/** One event of `{stream.id}`, narrowed by its kind. */",
            f"export type {name} =",
        ]
        for kind, schema in stream.events:
            payload = self._type_name(schema, f"{stream.base}{_pascal(kind)}")
            lines.append(
                f"\t| {{ readonly kind: {json.dumps(kind)}; readonly payload: {payload} }}"
            )
        lines[-1] += ";"
        lines.extend(
            [
                "",
                f"export function {name}(value: unknown, strict = false): value is {name} {{",
                "\tif (!isRecord(value)) return false;",
            ]
        )
        for kind, schema in stream.events:
            predicate = _member_validator("value.payload", schema, self)
            lines.append(
                f"\tif (value.kind === {json.dumps(kind)}) return {predicate};"
            )
        lines.extend(["\treturn false;", "}"])
        return lines

    def _render_operations(self) -> list[str]:
        surface = self._surface
        lines = [
            "/** Every operation this surface declares, as callable methods. */",
            f"export interface {surface.operations_type} {{",
        ]
        members = (*self._actions, *self._streams)
        lines.extend(_tree_lines(members, self._member_type))
        lines.extend(["}", ""])
        lines.extend(
            [
                (
                    f"export function {surface.factory}("
                    f"client: {surface.client_type}): {surface.operations_type} {{"
                ),
                "\treturn {",
            ]
        )
        lines.extend(_tree_body_lines(members, self._member_body))
        lines.extend(["\t};", "}", ""])
        lines.append(_call_helper(surface).rstrip("\n"))
        lines.append("")
        if self._streams:
            lines.append(_open_helper(surface).rstrip("\n"))
            lines.append("")
        return lines

    def _member_type(self, action: _Action | _Stream) -> str:
        if isinstance(action, _Stream):
            return self._stream_member_type(action)
        input_name = self._type_name(action.request, f"{action.base}Request")
        output_name = self._type_name(action.result, f"{action.base}Result")
        optional = "" if action.takes_input else "?"
        tail = _quote(action.id.rsplit(".", 1)[-1])
        return (
            f"readonly {tail}: (input{optional}: {input_name}, "
            f"options?: {self._surface.options_type}) => Promise<{output_name}>;"
        )

    def _stream_member_type(self, stream: _Stream) -> str:
        """A stream member takes its request, the handlers and the options.

        The request is never optional here: a required parameter cannot follow
        an optional one, and the handlers are what a subscription is for.
        """
        surface = self._surface
        input_name = self._type_name(stream.request, f"{stream.base}Request")
        tail = _quote(stream.id.rsplit(".", 1)[-1])
        return (
            f"readonly {tail}: (input: {input_name}, "
            f"handlers: {surface.stream_handlers_type}<{stream.event_type}>, "
            f"options?: {surface.options_type}) => "
            f"Promise<{surface.stream_handle_type}>;"
        )

    def _stream_member_body(self, stream: _Stream) -> str:
        surface = self._surface
        input_name = self._type_name(stream.request, f"{stream.base}Request")
        tail = stream.id.rsplit(".", 1)[-1]
        return (
            f"{_quote(tail)}: (input: {input_name}, "
            f"handlers: {surface.stream_handlers_type}<{stream.event_type}>, "
            f"options?: {surface.options_type}) =>\n"
            f"\t\t\t\topen<{stream.event_type}>(\n"
            f'\t\t\t\t\tclient, "{stream.id}", input, handlers, options,\n'
            f"\t\t\t\t\t{self._accepts(stream.request)},\n"
            f"\t\t\t\t\t{stream.event_type},\n"
            f"\t\t\t\t),"
        )

    def _member_body(self, action: _Action | _Stream) -> str:
        if isinstance(action, _Stream):
            return self._stream_member_body(action)
        input_name = self._type_name(action.request, f"{action.base}Request")
        output_name = self._type_name(action.result, f"{action.base}Result")
        tail = action.id.rsplit(".", 1)[-1]
        accepts_input = self._accepts(action.request)
        accepts_output = self._accepts(action.result)
        optional = "" if action.takes_input else "?"
        return (
            f"{_quote(tail)}: (input{optional}: {input_name}, "
            f"options?: {self._surface.options_type}) =>\n"
            f"\t\t\t\tcall<{output_name}>(\n"
            f'\t\t\t\t\tclient, "{action.id}", input, options,\n'
            f"\t\t\t\t\t{accepts_input},\n"
            f"\t\t\t\t\t{accepts_output},\n"
            f"\t\t\t\t),"
        )

    def _type_name(self, schema: Mapping[str, Any], fallback: str) -> str:
        return self.name_for(schema) or _inline_type(schema)

    def _accepts(self, schema: Mapping[str, Any]) -> str:
        """Return the predicate ``call`` should use for this value.

        A named object schema becomes its generated validator; anything else
        (``null``, a bare string, an enum) becomes an inline predicate, wrapped in
        a lambda because ``call`` takes a function either way.
        """
        name = self.name_for(schema)
        if name is not None:
            return name
        predicate = _inline_validator(schema, "candidate")
        return f"(candidate: unknown) => {predicate}"
