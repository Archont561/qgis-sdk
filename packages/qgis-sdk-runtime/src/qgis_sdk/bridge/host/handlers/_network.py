"""The one network fetch, which is a stream rather than a call."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._context import Host, HostHandler
from qgis_sdk.bridge.host._sources import Fetch
from qgis_sdk.bridge.host._support import fetch_request
from qgis_sdk.models.errors import QgisSdkBridgeError

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def network_fetch(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> Fetch:
    grant = ctx.authority.require_network(binding)
    if ctx.services.network is None:
        raise QgisSdkBridgeError("this host has no network transport configured")
    return Fetch(ctx.services.network, grant.constrain(fetch_request(payload)))


HANDLERS: dict[str, HostHandler] = {
    "network.fetch": network_fetch,
}
"""
Every declared id this module answers, and the function that answers it."""
