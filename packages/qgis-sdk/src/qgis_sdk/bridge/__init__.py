"""Host-side bridge contract: allowlisted operations, envelopes and dispatch.

Importing this package does not import Qt or QGIS, and it does not create a
transport: :class:`~qgis_sdk.bridge.dispatch.Dispatcher` works with plain
dictionaries, so the whole contract is testable without a running application.
The Qt side only has to deliver envelopes and send replies back.
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

__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "BridgeErrorCode",
    "BridgeOperation",
    "Dispatcher",
    "InvokeEnvelope",
    "ViewBinding",
    "failure",
    "success",
    "to_wire",
]
