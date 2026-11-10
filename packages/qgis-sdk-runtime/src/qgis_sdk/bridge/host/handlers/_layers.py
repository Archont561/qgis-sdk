"""Layers, rasters and the one file export that names a layer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import FileOperation
from qgis_sdk.bridge.host._context import HostHandler, _Host
from qgis_sdk.bridge.host._support import (
    _optional_int,
    _page_of,
    _plain,
)
from qgis_sdk.models import (
    CanvasPoint,
    layer_info,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def layers_list(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return _page_of(
        [layer_info(info) for info in ctx.services.layers.list_layers()], payload
    )


def layers_get(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
    return layer_info(ctx.services.layers.layer(payload["layer_id"]))


def layers_open_vector(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return _plain(ctx.services.layers.open_vector(path))


def layers_open_mesh(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return _plain(ctx.services.layers.open_mesh(path))


def layers_open_point_cloud(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return _plain(ctx.services.layers.open_point_cloud(path))


def layers_open_vector_tile(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return _plain(ctx.services.layers.open_vector_tile(path))


def layers_open_annotation(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    # An annotation layer is created inside the project, so the request
    # carries the name it is created under rather than a file to read: a
    # page that could name a path here would be asking to open a file the
    # authority never resolved.
    return _plain(ctx.services.layers.open_annotation(str(payload["name"])))


def layers_open_tiled_scene(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Any:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return _plain(ctx.services.layers.open_tiled_scene(path))


def rasters_open(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return ctx.rasters.open_raster(path).to_wire()


def rasters_get(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return ctx.rasters.raster(payload["layer_id"]).to_wire()


def rasters_statistics(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.rasters.statistics(payload["layer_id"], int(payload["band"])).to_wire()


def rasters_sample(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.rasters.sample(
        payload["layer_id"],
        CanvasPoint.from_wire(payload["point"]),
        band=_optional_int(payload.get("band")),
    ).to_wire()


def files_export(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    written = ctx.authority.export_file(binding, payload["file"], payload["content"])
    return {"bytes_written": written, "name": str(payload["file"].get("name", ""))}


HANDLERS: dict[str, HostHandler] = {
    "layers.list": layers_list,
    "layers.get": layers_get,
    "rasters.open": rasters_open,
    "rasters.get": rasters_get,
    "rasters.statistics": rasters_statistics,
    "rasters.sample": rasters_sample,
    "layers.open_vector": layers_open_vector,
    "layers.open_mesh": layers_open_mesh,
    "layers.open_point_cloud": layers_open_point_cloud,
    "layers.open_vector_tile": layers_open_vector_tile,
    "layers.open_annotation": layers_open_annotation,
    "layers.open_tiled_scene": layers_open_tiled_scene,
    "files.export": files_export,
}
"""
Every declared id this module answers, and the function that answers it."""
