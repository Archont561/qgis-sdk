"""Settings, notifications, styles, symbology and labelling."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._context import Host, HostHandler
from qgis_sdk.bridge.host._support import (
    page_of,
    wire,
)
from qgis_sdk.models import (
    labelling_from_wire,
    renderer_from_wire,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def settings_get(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
    return ctx.services.settings.get(payload["key"], payload.get("default"))


def notifications_info(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> None:
    ctx.services.notifications.info(payload["message"])


def styles_apply(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> None:
    ctx.services.styles.apply_style(payload["layer_id"], payload["style"])


def styles_list(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return page_of(ctx.services.styles.list_styles(payload.get("kind")), payload)


def styles_export(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
    return wire(
        ctx.services.styles.export_style(payload["layer_id"], payload["format"])
    )


def styles_import(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> None:
    ctx.services.styles.import_style(
        payload["layer_id"], payload["text"], payload["format"]
    )


def symbology_get(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
    return wire(ctx.services.styles.symbology(payload["layer_id"]))


def symbology_set(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> None:
    ctx.services.styles.set_symbology(
        payload["layer_id"], renderer_from_wire(payload["renderer"])
    )


def labelling_get(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
    return wire(ctx.services.styles.labelling(payload["layer_id"]))


def labelling_set(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> None:
    ctx.services.styles.set_labelling(
        payload["layer_id"], labelling_from_wire(payload["labelling"])
    )


HANDLERS: dict[str, HostHandler] = {
    "settings.get": settings_get,
    "notifications.info": notifications_info,
    "styles.apply": styles_apply,
    "symbology.get": symbology_get,
    "symbology.set": symbology_set,
    "labelling.get": labelling_get,
    "labelling.set": labelling_set,
    "styles.list": styles_list,
    "styles.export": styles_export,
    "styles.import": styles_import,
}
"""
Every declared id this module answers, and the function that answers it."""
