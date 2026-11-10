"""Writing one subscription out as server-sent events."""

from __future__ import annotations

import json
from queue import Empty
from typing import TYPE_CHECKING, Any

from ._queue import QgisSdkHostBusyError, QgisSdkHostReloadedError

if TYPE_CHECKING:  # pragma: no cover - typing only; the routes call this
    from ._endpoint import _Endpoint
    from ._handler import _RequestHandler
    from ._rest import _Subscription
    from ._sessions import _Session


def pump(handler: _RequestHandler, subscription: _Subscription) -> None:
    """Write the subscription's frames as events until it ends or the page goes away."""
    session = subscription.session
    try:
        _open(handler)
        while not session.closed and _step(handler, subscription, session):
            pass
    except (ConnectionError, OSError):
        pass  # The page went away; the subscription is disposed either way.


def _open(handler: _RequestHandler) -> None:
    """Answer 200 with the event-stream headers the browser's EventSource expects."""
    handler.connection.settimeout(handler.endpoint.write_timeout)
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()


def _step(
    handler: _RequestHandler, subscription: _Subscription, session: _Session
) -> bool:
    """Write one frame or keepalive and acknowledge it; ``False`` ends the stream."""
    if session.frames.empty() and not _flushed(handler.endpoint, session):
        return False
    frame = _taken(session)
    decoded: dict[str, Any] | None = None if frame is None else json.loads(frame)
    outgoing = b": keepalive\n\n" if frame is None else _event(frame)
    handler.wfile.write(outgoing)
    handler.wfile.flush()
    if decoded is None:
        return True
    if "terminal" in decoded:
        return False
    return _acknowledged(handler.endpoint, session, decoded)


def _event(frame: str) -> bytes:
    """One server-sent event carrying ``frame`` as its data line."""
    return b"data: " + frame.encode("utf-8") + b"\n\n"


def _taken(session: _Session) -> str | None:
    """The next frame that is ready now, or ``None`` when the buffer is still empty."""
    try:
        return session.frames.get(timeout=0.5)
    except Empty:
        return None


def _flushed(endpoint: _Endpoint, session: _Session) -> bool:
    """Ask the owner to push one more frame into the session; ``False`` when it cannot."""
    try:
        endpoint.queue.call(lambda: session.channel.flush(limit=1))
    except (QgisSdkHostBusyError, QgisSdkHostReloadedError):
        return False
    return True


def _acknowledged(
    endpoint: _Endpoint, session: _Session, decoded: dict[str, Any]
) -> bool:
    """Tell the host a frame was delivered, so a bounded in-flight window reopens.

    Written and flushed is what "delivered" means here: without the
    acknowledgement the in-flight bound stalls this stream after eight frames
    (decision-59).
    """
    subscription = decoded.get("subscription_id")
    seq = decoded.get("seq")
    if not isinstance(subscription, str) or not isinstance(seq, int):
        return True
    try:
        endpoint.queue.call(lambda: session.channel.acknowledge(subscription, seq))
    except (QgisSdkHostBusyError, QgisSdkHostReloadedError):
        return False
    return True
