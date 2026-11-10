"""The canvas operations: extent, scale, themes and the capture stream."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._context import HostHandler, _Host
from qgis_sdk.bridge.host._sources import _Capture, _WatchExtent
from qgis_sdk.models import ZoomTarget

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def canvas_extent(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return ctx.canvas.extent().to_wire()


def canvas_scale(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> float:
    return ctx.canvas.scale()


def canvas_crs(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> str | None:
    return ctx.canvas.crs()


def canvas_center(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return ctx.canvas.center().to_wire()


def canvas_zoom_to(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    target = ZoomTarget.from_wire(payload)
    return ctx.canvas.zoom_to(target).to_wire()


def canvas_refresh(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> None:
    ctx.canvas.refresh()


def canvas_themes(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return ctx.canvas.themes().to_wire()


def canvas_apply_theme(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.canvas.apply_theme(payload["name"]).to_wire()


def canvas_extent_changed(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> _WatchExtent:
    return _WatchExtent(ctx.canvas)


def canvas_capture(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> _Capture:
    return _Capture(ctx.canvas, payload["shape"])


HANDLERS: dict[str, HostHandler] = {
    "canvas.capture": canvas_capture,
    "canvas.center": canvas_center,
    "canvas.crs": canvas_crs,
    "canvas.extent": canvas_extent,
    "canvas.extent_changed": canvas_extent_changed,
    "canvas.refresh": canvas_refresh,
    "canvas.scale": canvas_scale,
    "canvas.themes": canvas_themes,
    "canvas.apply_theme": canvas_apply_theme,
    "canvas.zoom_to": canvas_zoom_to,
}
"""
Every declared id this module answers, and the function that answers it."""
