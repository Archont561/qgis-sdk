"""The operation handlers, one module per namespace of the declared ids.

``HANDLERS`` is the single table the registration reads: each module answers the
ids its own namespace declares, and nothing else may answer them.
"""

from __future__ import annotations

from qgis_sdk.bridge.host._context import HostHandler as _HostHandler
from qgis_sdk.bridge.host.handlers import (
    _algorithms,
    _canvas,
    _connections,
    _features,
    _layers,
    _network,
    _project,
    _styles,
)

HANDLERS: dict[str, _HostHandler] = {
    **_algorithms.HANDLERS,
    **_canvas.HANDLERS,
    **_connections.HANDLERS,
    **_features.HANDLERS,
    **_layers.HANDLERS,
    **_network.HANDLERS,
    **_project.HANDLERS,
    **_styles.HANDLERS,
}
"""Every declared id and the handler that answers it."""

__all__ = ["HANDLERS"]
