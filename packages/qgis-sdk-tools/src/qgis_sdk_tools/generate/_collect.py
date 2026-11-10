"""Reading a plugin description into the actions and streams to render."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError

from qgis_sdk_tools.generate._contract import _EVENT_KINDS
from qgis_sdk_tools.generate._emit import _pascal
from qgis_sdk_tools.generate._names import (
    _Action,
    _declared_name,
    _Stream,
)


def _by_id(entry: Any) -> str:
    """Sort operations by id, so the rendering order never depends on the file."""
    return str(entry["id"])


def _declared_name_of(
    raw: Mapping[str, Any], field: str, fallback: str, kind: str, operation_id: str
) -> str:
    """The name an operation declared for its request or its result."""
    return _declared_name(raw.get(field), fallback, kind=kind, action=operation_id)


def _declared_str(raw: Mapping[str, Any], field: str) -> str | None:
    """The declared override, when it really is a string."""
    value = raw.get(field)
    return value if isinstance(value, str) else None


def _action_schemas(
    raw: Mapping[str, Any], action_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Take the request and result an action declares, or say what is missing."""
    if "events" in raw:
        raise QgisSdkBridgeError(
            f"{action_id}: an action answers with a result; a stream "
            "declares events and belongs in description.streams"
        )
    request = raw.get("request")
    result = raw.get("result")
    if not isinstance(request, Mapping) or not isinstance(result, Mapping):
        raise QgisSdkBridgeError(
            f"{action_id}: the generator needs declared request and result schemas"
        )
    return request, result


def _known_event_kinds(events: Mapping[str, Any], stream_id: str) -> None:
    """Refuse an event kind the frame does not carry."""
    unknown = sorted(str(kind) for kind in events if kind not in _EVENT_KINDS)
    if unknown:
        raise QgisSdkBridgeError(
            f"{stream_id}: {', '.join(unknown)} is not a stream event kind; "
            f"the frame carries {', '.join(_EVENT_KINDS)}"
        )


def _stream_schemas(
    raw: Mapping[str, Any], stream_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Take the request and the events a stream declares, checked."""
    if "result" in raw:
        raise QgisSdkBridgeError(f"{stream_id}: a stream declares events, not a result")
    request = raw.get("request")
    events = raw.get("events")
    if not isinstance(request, Mapping) or not isinstance(events, Mapping):
        raise QgisSdkBridgeError(
            f"{stream_id}: the generator needs a declared request schema "
            "and an events map"
        )
    if not events:
        raise QgisSdkBridgeError(
            f"{stream_id}: a stream declares at least one event kind"
        )
    _known_event_kinds(events, stream_id)
    for kind, schema in events.items():
        if not isinstance(schema, Mapping):
            raise QgisSdkBridgeError(
                f"{stream_id}: events.{kind} must be a schema object"
            )
    return request, events


class _Collector:
    """Turn one declared description into the operations the generator renders.

    The description is data a plugin already has; this checks it and gives every
    request, result and event schema its name on the way through, because the
    names are decided while the tree is still being walked.
    """

    def __init__(
        self,
        description: Mapping[str, Any],
        ids: set[str],
        names: Any,
    ) -> None:
        self._description = description
        self._ids = ids
        self._names = names

    def actions(self) -> tuple[_Action, ...]:
        """The declared actions, in id order, with their schemas named."""
        return tuple(
            self._action(raw)
            for raw in sorted(self._description["actions"], key=_by_id)
        )

    def streams(self) -> tuple[_Stream, ...]:
        """The declared streams, in id order, with their schemas named."""
        return tuple(
            self._stream(raw)
            for raw in sorted(self._description.get("streams") or [], key=_by_id)
        )

    def _claim(self, operation_id: str) -> None:
        """Hold actions and streams to one id namespace (decision-28)."""
        if operation_id in self._ids:
            raise QgisSdkBridgeError(f"duplicate operation id {operation_id!r}")
        self._ids.add(operation_id)

    def _action(self, raw: Mapping[str, Any]) -> _Action:
        action_id = str(raw["id"])
        self._claim(action_id)
        request, result = _action_schemas(raw, action_id)
        base = _pascal(action_id)
        self._names.declare(
            request,
            _declared_name_of(
                raw, "request_name", f"{base}Request", "request", action_id
            ),
        )
        self._names.declare(
            result,
            _declared_name_of(raw, "result_name", f"{base}Result", "result", action_id),
        )
        return _Action(
            id=action_id,
            base=base,
            request=request,
            result=result,
            takes_input=bool(request.get("required")),
            request_name=_declared_str(raw, "request_name"),
            result_name=_declared_str(raw, "result_name"),
        )

    def _stream(self, raw: Mapping[str, Any]) -> _Stream:
        stream_id = str(raw["id"])
        self._claim(stream_id)
        request, events = _stream_schemas(raw, stream_id)
        base = _pascal(stream_id)
        self._names.declare(
            request,
            _declared_name_of(
                raw, "request_name", f"{base}Request", "request", stream_id
            ),
        )
        declared = tuple(
            (kind, events[kind]) for kind in _EVENT_KINDS if kind in events
        )
        for kind, schema in declared:
            self._names.declare(schema, f"{base}{_pascal(kind)}")
        return _Stream(
            id=stream_id,
            base=base,
            request=request,
            events=declared,
            request_name=_declared_str(raw, "request_name"),
        )
