"""The frames around the operations: errors, streams, and the schema map."""

from __future__ import annotations

import json

from qgis_sdk_tools.generate._context import Rendering
from qgis_sdk_tools.generate._contract import (
    _EVENT_KINDS,
    _TERMINAL_KINDS,
    CONTRACT_ERROR_CODE,
)
from qgis_sdk_tools.generate._emit import (
    _member_validator,
    pascal,
    quote,
)
from qgis_sdk_tools.generate._names import Stream


class Frames:
    """Everything the generated module carries besides its operation members.

    The error class, the stream support types, the ``Operations``/``Streams``
    maps and one event union per stream: rendering them is a function of the
    surface and the declared operations, never of the render order.
    """

    def __init__(self, rendering: Rendering) -> None:
        self._surface = rendering.surface
        self._actions = rendering.actions
        self._streams = rendering.streams
        self._names = rendering.names

    def error_class_lines(self) -> list[str]:
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

    def event_union_lines(self, stream: Stream) -> list[str]:
        """Render the event union of one stream, without a predicate."""
        lines = [
            f"/** One event of `{stream.id}`, narrowed by its kind. */",
            f"export type {stream.event_type} =",
        ]
        for kind, schema in stream.events:
            payload = self._names.type_name(schema, f"{stream.base}{pascal(kind)}")
            lines.append(
                f"\t| {{ readonly kind: {json.dumps(kind)}; readonly payload: {payload} }}"
            )
        lines[-1] += ";"
        return lines

    def schema_map_lines(self) -> list[str]:
        """Render ``Operations`` and ``Streams``, keyed by the full operation id."""
        return [
            "/** The declared actions by id: what goes in and what comes back. */",
            *self._operations_map(),
            "",
            "/** The declared streams by id: what goes in and the events that come out. */",
            *self._streams_map(),
            "",
        ]

    def _operations_map(self) -> list[str]:
        if not self._actions:
            return ["export type Operations = Record<never, never>;"]
        lines = ["export interface Operations {"]
        for action in self._actions:
            request = self._names.type_name(action.request, f"{action.base}Request")
            result = self._names.type_name(action.result, f"{action.base}Result")
            lines.append(
                f"\treadonly {quote(action.id)}: {{ readonly request: {request}; "
                f"readonly result: {result} }};"
            )
        lines.append("}")
        return lines

    def _streams_map(self) -> list[str]:
        if not self._streams:
            return ["export type Streams = Record<never, never>;"]
        lines = ["export interface Streams {"]
        for stream in self._streams:
            request = self._names.type_name(stream.request, f"{stream.base}Request")
            lines.append(
                f"\treadonly {quote(stream.id)}: {{ readonly request: {request}; "
                f"readonly event: {stream.event_type} }};"
            )
        lines.append("}")
        return lines

    def subscribe_lines(self) -> list[str]:
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

    def stream_support_lines(self) -> list[str]:
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

    def event_lines(self, stream: Stream) -> list[str]:
        """Render the event union of one stream and the predicate that narrows it."""
        name = stream.event_type
        lines = [
            f"/** One event of `{stream.id}`, narrowed by its kind. */",
            f"export type {name} =",
        ]
        for kind, schema in stream.events:
            payload = self._names.type_name(schema, f"{stream.base}{pascal(kind)}")
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
            predicate = _member_validator("value.payload", schema, self._names)
            lines.append(
                f"\tif (value.kind === {json.dumps(kind)}) return {predicate};"
            )
        lines.extend(["\treturn false;", "}"])
        return lines
