"""The project operations: tree, layers, CRS, variables and bookmarks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import FileOperation
from qgis_sdk.bridge.host._context import HostHandler, _Host
from qgis_sdk.bridge.host._sources import _WatchProject
from qgis_sdk.bridge.host._support import (
    _optional_int,
    _page_of,
)
from qgis_sdk.models import CanvasExtent

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def project_layer_ids(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return _page_of(ctx.services.project.layer_ids(), payload)


def project_tree(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return ctx.project.layer_tree().to_wire()


def project_add_layer(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.project.add_layer(
        payload["layer_id"], group=payload.get("group")
    ).to_wire()


def project_remove_layer(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.project.remove_layer(payload["layer_id"]).to_wire()


def project_move_layer(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.project.move_layer(
        payload["layer_id"],
        group=payload.get("group"),
        index=_optional_int(payload.get("index")),
    ).to_wire()


def project_set_visible(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.project.set_visible(
        payload["node_id"], bool(payload["visible"])
    ).to_wire()


def project_crs(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> str | None:
    return ctx.project.crs()


def project_set_crs(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> str:
    return ctx.project.set_crs(payload["auth_id"])


def project_variables(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [entry.to_wire() for entry in ctx.project.variables()]


def project_set_variable(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [
        entry.to_wire()
        for entry in ctx.project.set_variable(payload["name"], payload["value"])
    ]


def project_unset_variable(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [entry.to_wire() for entry in ctx.project.unset_variable(payload["name"])]


def project_properties(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [entry.to_wire() for entry in ctx.project.custom_properties()]


def project_set_property(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [
        entry.to_wire()
        for entry in ctx.project.set_custom_property(payload["name"], payload["value"])
    ]


def project_unset_property(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [
        entry.to_wire() for entry in ctx.project.unset_custom_property(payload["name"])
    ]


def project_bookmarks(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [bookmark.to_wire() for bookmark in ctx.project.bookmarks()]


def project_bookmark(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return ctx.project.bookmark(payload["name"]).to_wire()


def project_add_bookmark(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [
        bookmark.to_wire()
        for bookmark in ctx.project.add_bookmark(
            payload["name"], CanvasExtent.from_wire(payload["extent"])
        )
    ]


def project_remove_bookmark(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> list:
    return [
        bookmark.to_wire() for bookmark in ctx.project.remove_bookmark(payload["name"])
    ]


def project_read(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return ctx.project.read(path).to_wire()


def project_write(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.WRITE)
    return ctx.project.write(
        path, overwrite=bool(payload.get("overwrite", False))
    ).to_wire()


def project_save(ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return ctx.project.save().to_wire()


def project_changed(
    ctx: _Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> _WatchProject:
    return _WatchProject(ctx.project)


HANDLERS: dict[str, HostHandler] = {
    "project.layer_ids": project_layer_ids,
    "project.tree": project_tree,
    "project.add_layer": project_add_layer,
    "project.remove_layer": project_remove_layer,
    "project.move_layer": project_move_layer,
    "project.set_visible": project_set_visible,
    "project.crs": project_crs,
    "project.set_crs": project_set_crs,
    "project.variables": project_variables,
    "project.set_variable": project_set_variable,
    "project.unset_variable": project_unset_variable,
    "project.properties": project_properties,
    "project.set_property": project_set_property,
    "project.unset_property": project_unset_property,
    "project.bookmarks": project_bookmarks,
    "project.bookmark": project_bookmark,
    "project.add_bookmark": project_add_bookmark,
    "project.remove_bookmark": project_remove_bookmark,
    "project.read": project_read,
    "project.write": project_write,
    "project.save": project_save,
    "project.changed": project_changed,
}
"""
Every declared id this module answers, and the function that answers it."""
