"""The operation members: one method per action and per stream."""

from __future__ import annotations

from qgis_sdk_tools.generate._context import Rendering
from qgis_sdk_tools.generate._emit import (
    _quote,
    call_helper,
    open_helper,
    tree_body_lines,
    tree_lines,
)
from qgis_sdk_tools.generate._names import Action, Stream


class Members:
    """The typed surface of the generated client: one member per operation.

    An action is a ``call`` and a stream is an ``open``, so both the interface
    and the object literal are written from the same declared operation - the
    member name is the id's last segment, quoted because an id may carry dots.
    """

    def __init__(self, rendering: Rendering) -> None:
        self._surface = rendering.surface
        self._actions = rendering.actions
        self._streams = rendering.streams
        self._names = rendering.names

    def operations(self) -> list[str]:
        surface = self._surface
        lines = [
            "/** Every operation this surface declares, as callable methods. */",
            f"export interface {surface.operations_type} {{",
        ]
        members = (*self._actions, *self._streams)
        lines.extend(tree_lines(members, self.member_type))
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
        lines.extend(tree_body_lines(members, self.member_body))
        lines.extend(["\t};", "}", ""])
        lines.append(call_helper(surface).rstrip("\n"))
        lines.append("")
        if self._streams:
            lines.append(open_helper(surface).rstrip("\n"))
            lines.append("")
        return lines

    def member_type(self, action: Action | Stream) -> str:
        if isinstance(action, Stream):
            return self.stream_member_type(action)
        input_name = self._names.type_name(action.request, f"{action.base}Request")
        output_name = self._names.type_name(action.result, f"{action.base}Result")
        optional = "" if action.takes_input else "?"
        tail = _quote(action.id.rsplit(".", 1)[-1])
        return (
            f"readonly {tail}: (input{optional}: {input_name}, "
            f"options?: {self._surface.options_type}) => Promise<{output_name}>;"
        )

    def stream_member_type(self, stream: Stream) -> str:
        """A stream member takes its request, the handlers and the options.

        The request is never optional here: a required parameter cannot follow
        an optional one, and the handlers are what a subscription is for.
        """
        surface = self._surface
        input_name = self._names.type_name(stream.request, f"{stream.base}Request")
        tail = _quote(stream.id.rsplit(".", 1)[-1])
        return (
            f"readonly {tail}: (input: {input_name}, "
            f"handlers: {surface.stream_handlers_type}<{stream.event_type}>, "
            f"options?: {surface.options_type}) => "
            f"Promise<{surface.stream_handle_type}>;"
        )

    def stream_member_body(self, stream: Stream) -> str:
        surface = self._surface
        input_name = self._names.type_name(stream.request, f"{stream.base}Request")
        tail = stream.id.rsplit(".", 1)[-1]
        return (
            f"{_quote(tail)}: (input: {input_name}, "
            f"handlers: {surface.stream_handlers_type}<{stream.event_type}>, "
            f"options?: {surface.options_type}) =>\n"
            f"\t\t\t\topen<{stream.event_type}>(\n"
            f'\t\t\t\t\tclient, "{stream.id}", input, handlers, options,\n'
            f"\t\t\t\t\t{self._names.accepts(stream.request)},\n"
            f"\t\t\t\t\t{stream.event_type},\n"
            f"\t\t\t\t),"
        )

    def member_body(self, action: Action | Stream) -> str:
        if isinstance(action, Stream):
            return self.stream_member_body(action)
        input_name = self._names.type_name(action.request, f"{action.base}Request")
        output_name = self._names.type_name(action.result, f"{action.base}Result")
        tail = action.id.rsplit(".", 1)[-1]
        accepts_input = self._names.accepts(action.request)
        accepts_output = self._names.accepts(action.result)
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
