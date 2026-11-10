"""The two REST routes: one call, and one event stream."""

from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge import BRIDGE_PROTOCOL_VERSION

from ._errors import error_status
from ._queue import QgisSdkHostBusyError, QgisSdkHostReloadedError
from ._stream import pump

if TYPE_CHECKING:  # pragma: no cover - typing only; the handler imports these routes
    from ._endpoint import _Endpoint
    from ._handler import _RequestHandler
    from ._sessions import _Session, _Sessions


class QgisSdkRefusal(Exception):
    """A route's answer that is not a result: the reply an error is written from."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)
        self.payload = payload


@dataclass(frozen=True)
class _Subscription:
    """One open event stream: the session it writes into, and the id that disposes it."""

    sessions: _Sessions
    session_id: str
    session: _Session

    def close(self) -> None:
        """Mark the stream finished and let the owner thread dispose of it."""
        self.session.closed = True
        self.sessions.dispose_later(self.session_id)


def call_action(handler: _RequestHandler) -> None:
    """Answer one ``/actions/<id>`` request with the operation's result."""
    endpoint = handler.endpoint
    action = _named(handler.path, endpoint.runtime.actions, endpoint.allowed)
    if action is None:
        handler.send_error(404)
        return
    payload = handler.json_object_body()
    if payload is None:
        return
    try:
        result = endpoint.queue.call(lambda: _dispatched(endpoint, action, payload))
    except (QgisSdkHostBusyError, QgisSdkHostReloadedError) as error:
        handler.answer(503, _failure(error))
        return
    handler.answer(200 if "value" in result else error_status(result), result)


def open_stream(handler: _RequestHandler) -> None:
    """Answer one ``/streams/<id>`` request by following the stream until it ends."""
    endpoint = handler.endpoint
    stream_id = _named(handler.path, endpoint.runtime.streams, endpoint.allowed)
    if stream_id is None:
        handler.send_error(404)
        return
    payload = handler.json_object_body()
    if payload is None:
        return
    if not endpoint.event_slots.acquire(blocking=False):
        handler.send_error(503)
        return
    try:
        _served(handler, stream_id, payload)
    finally:
        endpoint.event_slots.release()


def _served(handler: _RequestHandler, stream_id: str, payload: dict[str, Any]) -> None:
    """Subscribe the stream and pump it, or answer with why it could not start."""
    try:
        _follow(handler, _subscribed(handler.endpoint, stream_id, payload))
    except QgisSdkRefusal as refusal:
        handler.answer(error_status(refusal.payload), refusal.payload)
    except (QgisSdkHostBusyError, QgisSdkHostReloadedError) as error:
        handler.answer(503, _failure(error))
    except (ConnectionError, OSError):
        pass  # the page went away; the session is disposed either way


def _follow(handler: _RequestHandler, subscription: _Subscription) -> None:
    """Pump one subscription and dispose it whichever way the pump ends."""
    try:
        pump(handler, subscription)
    finally:
        subscription.close()


def _dispatched(
    endpoint: _Endpoint, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Run one call on the owner thread, disposing its session whichever way it ends."""
    capacity = endpoint.sessions.capacity_error()
    if capacity is not None:
        return capacity
    session_id, session = endpoint.sessions.open()
    try:
        return _reply(session, action, payload)
    finally:
        endpoint.sessions.dispose(session_id)


def _reply(session: _Session, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one call envelope and read the reply it produced."""
    text = json.dumps(
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": secrets.token_hex(8),
            "operation": action,
            "payload": payload,
        }
    )
    if not session.channel.receive(text) or not session.replies:
        return _invalid_request()
    reply = json.loads(session.replies.pop(0))
    if reply.get("ok"):
        return {"value": reply["value"]}
    return {"error": reply["error"]}


def _subscribed(
    endpoint: _Endpoint, stream_id: str, payload: dict[str, Any]
) -> _Subscription:
    """Start one subscription in the owner's turn, or refuse it there."""
    return endpoint.queue.call(lambda: _started(endpoint, stream_id, payload))


def _started(
    endpoint: _Endpoint, stream_id: str, payload: dict[str, Any]
) -> _Subscription:
    """Open the session and subscribe it; a refusal disposes the session it opened."""
    capacity = endpoint.sessions.capacity_error()
    if capacity is not None:
        raise QgisSdkRefusal(capacity)
    session_id, session = endpoint.sessions.open(defer_on_overflow=True)
    text = json.dumps(
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": secrets.token_hex(8),
            "operation": stream_id,
            "payload": payload,
        }
    )
    if not session.channel.receive(text) or not session.replies:
        endpoint.sessions.dispose(session_id)
        raise QgisSdkRefusal(_invalid_request())
    reply = json.loads(session.replies.pop(0))
    if not reply.get("ok"):
        endpoint.sessions.dispose(session_id)
        raise QgisSdkRefusal({"error": reply["error"]})
    return _Subscription(endpoint.sessions, session_id, session)


def _named(path: str, declared: Sequence[str], allowed: frozenset[str]) -> str | None:
    """The id a REST path names, when the runtime declares it and the host allows it."""
    parts = path.split("/")
    name = parts[2] if len(parts) == 3 else ""
    return name if name in declared and name in allowed else None


def _invalid_request() -> dict[str, Any]:
    """The reply for an envelope the bridge could not answer at all."""
    return {"error": {"code": "invalid_request", "message": "Invalid request"}}


def _failure(error: Exception) -> dict[str, Any]:
    """The reply for a host that is busy or has gone away under the request."""
    return {
        "error": {"code": getattr(error, "code", "host_busy"), "message": str(error)}
    }
