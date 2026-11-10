"""The one network fetch, which is a stream rather than a call."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._context import HostHandler, _Host
from qgis_sdk.bridge.host._sources import _Fetch
from qgis_sdk.bridge.host._support import _fetch_request
from qgis_sdk.models.errors import QgisSdkBridgeError

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def network_fetch(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> _Fetch:
    grant = ctx.authority.require_network(binding)
    if ctx.services.network is None:
        raise QgisSdkBridgeError("this host has no network transport configured")
    return _Fetch(ctx.services.network, grant.constrain(_fetch_request(payload)))


HANDLERS: dict[str, HostHandler] = {
    "network.fetch": network_fetch,
}
"""
Every declared id this module answers, and the function that answers it."""
