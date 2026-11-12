"""Connection profiles, their auth configurations, and browsing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._context import Host, HostHandler
from qgis_sdk.bridge.host._support import (
    page_of,
    wire,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def connections_list(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return page_of(ctx.connections.list_connections(), payload)


def connections_describe(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    return wire(ctx.connections.connection(payload["provider"], payload["connection"]))


def connections_browse(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return page_of(
        ctx.connections.browse(
            payload["provider"], payload["connection"], payload.get("schema")
        ),
        payload,
    )


def connections_open_layer(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    return wire(
        ctx.connections.open_layer(
            payload["provider"],
            payload["connection"],
            payload["schema"],
            payload["item"],
        )
    )


def connections_test(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    return wire(ctx.connections.test(payload["provider"], payload["connection"]))


def auth_configurations(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return page_of(ctx.connections.auth_configurations(), payload)


def auth_attach(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> None:
    ctx.connections.attach_auth_config(
        payload["provider"], payload["connection"], payload["auth_config"]
    )


HANDLERS: dict[str, HostHandler] = {
    "connections.list": connections_list,
    "connections.describe": connections_describe,
    "connections.browse": connections_browse,
    "connections.open_layer": connections_open_layer,
    "connections.test": connections_test,
    "auth.configurations": auth_configurations,
    "auth.attach": auth_attach,
}
"""
Every declared id this module answers, and the function that answers it."""
