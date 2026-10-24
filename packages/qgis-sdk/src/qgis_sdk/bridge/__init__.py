"""Host-side bridge contract: allowlisted operations, envelopes, streams, dispatch.

Importing this package does not import Qt or QGIS, and it does not create a
transport: :class:`~qgis_sdk.bridge.dispatch.Dispatcher` works with plain
dictionaries, so the whole contract - including subscriptions, their ordering
and their bounded buffers - is testable without a running application. The Qt
side only has to deliver envelopes, send replies back and pump the frames.
"""

from __future__ import annotations

from qgis_sdk.bridge.dispatch import Dispatcher, ViewBinding
from qgis_sdk.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeErrorCode,
    BridgeOperation,
    InvokeEnvelope,
    failure,
    success,
    to_wire,
)
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
    MAX_QUEUED_EVENTS,
    StreamEventType,
    StreamTerminal,
    Subscription,
)

__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "MAX_FRAMES_PER_PUMP",
    "MAX_QUEUED_EVENTS",
    "BridgeErrorCode",
    "BridgeOperation",
    "Dispatcher",
    "InvokeEnvelope",
    "StreamEventType",
    "StreamTerminal",
    "Subscription",
    "ViewBinding",
    "failure",
    "success",
    "to_wire",
]
