"""What one request may reach, assembled once when the listener starts."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ._queue import GuiQueue
    from ._sessions import _Sessions


@dataclass(frozen=True)
class _Endpoint:
    """The listener's state as a request handler sees it.

    Frozen and built once: a handler reads the queue, the session book, the
    allowlist, its deadlines and the closed flag from here rather than reaching
    back into the façade that owns the lifecycle. That keeps the request path
    and the shutdown path from having to know each other's fields.
    """

    runtime: Any
    allowed: frozenset[str]
    queue: GuiQueue
    sessions: _Sessions
    token: str
    read_timeout: float
    write_timeout: float
    grace: float
    event_slots: threading.BoundedSemaphore
    closed: threading.Event
