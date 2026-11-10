"""The generator: collect the schema pieces, then render them in a fixed order."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from qgis_sdk_tools.generate._collect import _Collector
from qgis_sdk_tools.generate._context import _Rendering
from qgis_sdk_tools.generate._contract import (
    GENERATED_MARKER,
    PLUGIN_SURFACE,
    _Surface,
    contract_fingerprint,
)
from qgis_sdk_tools.generate._emit import (
    _interface_lines,
    _json_lines,
    _sorted_declaration,
    _validator_lines,
)
from qgis_sdk_tools.generate._frames import _Frames
from qgis_sdk_tools.generate._members import _Members
from qgis_sdk_tools.generate._names import _Action, _check_sdk_tree, _Stream
from qgis_sdk_tools.generate._naming import _Naming


class _Generator:
    """One plugin description in, one TypeScript module out.

    The work is split by when it may happen, because the order is the contract:
    ``_Naming`` decides every exported type name, ``_Collector`` reads the
    declared operations and asks it for those names, and only then do
    ``_Frames`` and ``_Members`` render - a parent's field type has to be a name
    already chosen, never one still on its way out of the walk.
    """

    def __init__(
        self, description: Mapping[str, Any], *, surface: _Surface = PLUGIN_SURFACE
    ) -> None:
        self._description = description
        self._surface = surface
        self._ids: set[str] = set()
        self._naming = _Naming()
        collector = _Collector(description, self._ids, self._naming)
        self._actions: tuple[_Action, ...] = collector.actions()
        self._streams: tuple[_Stream, ...] = collector.streams()
        rendering = _Rendering(
            surface=surface,
            actions=self._actions,
            streams=self._streams,
            names=self._naming,
        )
        self._frames = _Frames(rendering)
        self._members = _Members(rendering)

    def name_for(self, schema: Mapping[str, Any]) -> str | None:
        """Return the registered name of an object schema, if it has one."""
        return self._naming.name_for(schema)

    # -- rendering -----------------------------------------------------

    def render(self) -> str:
        """Render the plugin module: the client, its validators, its operations."""
        lines = [
            *self._header_lines(),
            *self._client_lines(),
            *self._guard_lines(),
            *self._object_blocks(_interface_lines),
            *self._object_blocks(_validator_lines),
            *self._stream_blocks(self._frames.event_lines),
            *self._members.operations(),
        ]
        return "\n".join(lines).rstrip("\n") + "\n"

    def render_schema(self, *, sdk_import: str) -> str:
        """Render the schema module: types plus the declaration, no code."""
        _check_sdk_tree(self._ids)
        lines = [
            *self._schema_header(sdk_import),
            *self._object_blocks(_interface_lines),
            *self._stream_blocks(self._frames.event_union_lines),
            *self._frames.schema_map_lines(),
            *self._declaration_lines(),
        ]
        return "\n".join(lines).rstrip("\n") + "\n"

    # -- the pieces of a rendering -------------------------------------

    def _header_lines(self) -> list[str]:
        """The banner, the surface's imports, and the module's own constants."""
        described = self._description
        surface = self._surface
        return [
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
        ]

    def _client_lines(self) -> list[str]:
        """The operation ids, the options and the client the module wraps."""
        surface = self._surface
        return [
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
            *self._frames.subscribe_lines(),
            "}",
            "",
        ]

    def _guard_lines(self) -> list[str]:
        """The error and stream types, then the guards every validator uses."""
        return [
            *self._frames.stream_support_lines(),
            *self._frames.error_class_lines(),
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

    def _object_blocks(self, render: Any) -> list[str]:
        """One block per named object, rendered by ``render``, in name order."""
        lines: list[str] = []
        for name, schema in sorted(self._naming.objects):
            lines.extend(render(schema, name, self))
            lines.append("")
        return lines

    def _stream_blocks(self, render: Any) -> list[str]:
        """One block per stream, rendered by ``render``, in declaration order."""
        lines: list[str] = []
        for stream in self._streams:
            lines.extend(render(stream))
            lines.append("")
        return lines

    def _schema_header(self, sdk_import: str) -> list[str]:
        """The banner and constants of a schema module, which imports nothing else."""
        described = self._description
        return [
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
            f"export const PLUGIN_ID = {json.dumps(described.get('id', ''))};",
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

    def _declaration_lines(self) -> list[str]:
        """The declaration the plugin already emitted, typed by the module above."""
        return [
            "/** The declaration `describe(app)` emitted, carrying the types above. */",
            (
                "const schema: BridgeSchema<Operations, Streams> = "
                "defineBridgeSchema<Operations, Streams>({"
            ),
            *_json_lines(_sorted_declaration(self._description)),
            "});",
            "",
            "export default schema;",
        ]
