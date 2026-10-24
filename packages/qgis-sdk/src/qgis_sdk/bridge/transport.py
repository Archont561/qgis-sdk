"""Carry the bridge's envelopes over a channel that moves strings.

A QWebChannel moves JSON text between a page and a ``QObject``. That is the
whole of its contract, and it is deliberately the whole of this module's too:
:class:`ChannelTransport` takes text in, asks the dispatcher, and hands text
back through a callback. Nothing here imports Qt, so the adapter's behaviour -
correlation, refusal of malformed text, subscription frames, disposal - is
tested without a browser, and the Qt object that wraps it stays small enough to
read in one screen (see :mod:`qgis_sdk.adapters.webchannel`).

Two habits matter at this layer.

*A message that is not JSON cannot be answered.* There is no call id to
correlate a refusal with, so it is counted and dropped rather than answered with
a reply the page could not place.

*The transport never decides anything.* Authorization, the allowlist, ordering
and buffering all live in the dispatcher; this module only moves text.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.bridge.dispatch import Dispatcher, ViewBinding
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION
from qgis_sdk.bridge.streams import MAX_FRAMES_PER_PUMP


@dataclass(slots=True)
class ChannelTransport:
    """Move envelopes between a channel and one view's dispatcher."""

    dispatcher: Dispatcher
    binding: ViewBinding
    send: Callable[[str], None]
    refused: int = field(default=0)

    def receive(self, text: str) -> bool:
        """Handle one message from the channel; ``False`` if it was unusable.

        The reply is sent through :attr:`send` before this returns, so a caller
        never has to remember to flush after a call.
        """
        if not isinstance(text, str):
            self.refused += 1
            return False
        try:
            message: Any = json.loads(text)
        except (TypeError, ValueError):
            self.refused += 1
            return False
        if not isinstance(message, Mapping):
            self.refused += 1
            return False
        # Invocations, subscriptions, disposals and releases all arrive here as
        # the same text and leave through the same narrow entry point.
        reply = self.dispatcher.dispatch(self.binding, message)
        self._send_reply(reply)
        return True

    def flush(self, *, limit: int = MAX_FRAMES_PER_PUMP) -> int:
        """Send the frames waiting for this view; return how many went out."""
        frames = self.dispatcher.pump(self.binding, limit=limit)
        for frame in frames:
            self.send(json.dumps(frame, separators=(",", ":"), sort_keys=True))
        return len(frames)

    def dispose(self) -> int:
        """Close every subscription this view opened."""
        return self.dispatcher.dispose(self.binding)

    def _send_reply(self, reply: Mapping[str, Any]) -> None:
        self.send(json.dumps(reply, separators=(",", ":"), sort_keys=True))


def envelope_protocol() -> int:
    """The protocol version this transport speaks, for a host to advertise."""
    return BRIDGE_PROTOCOL_VERSION


__all__ = ["ChannelTransport", "envelope_protocol"]
