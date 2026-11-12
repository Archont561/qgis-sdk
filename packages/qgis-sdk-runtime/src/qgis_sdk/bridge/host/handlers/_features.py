"""Features, expressions, blobs and the editing sessions over them."""

from __future__ import annotations

import base64
from collections.abc import Iterator, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._context import Host, HostHandler
from qgis_sdk.bridge.host._schemas import BLOB_CHUNK_BYTES
from qgis_sdk.bridge.host._support import (
    feature_query,
    geometry,
    optional_int,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def blob_get(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    offset = int(payload.get("offset", 0))
    length = int(payload.get("length", BLOB_CHUNK_BYTES))
    ref = ctx.authority.blob_info(binding, payload["blob"])
    chunk = ctx.authority.read_blob(
        binding, payload["blob"], offset=offset, length=length
    )
    end = offset + len(chunk)
    return {
        "offset": offset,
        "length": len(chunk),
        "size": ref.size,
        "media_type": ref.media_type,
        "checksum": ref.checksum,
        "data_base64": base64.b64encode(chunk).decode("ascii"),
        "next_offset": None if end >= ref.size else end,
    }


def features_page(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    """Stream pages until the layer runs out, one bounded page per event.

    The pull shape is the point: the host asks the provider for one page,
    hands it to the view, and stops until the view pumps again. A page that
    stops early has cost the host one page, not the dataset.
    """
    service = ctx.features
    layer_id = payload["layer_id"]
    query = feature_query(payload)

    def pages() -> Iterator[dict[str, Any]]:
        cursor = query.cursor
        while True:
            page = service.page(layer_id, replace(query, cursor=cursor))
            yield page.to_wire()
            if not page.truncated or page.next_cursor is None:
                return
            cursor = page.next_cursor

    return pages()


def features_get(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    service = ctx.features
    feature = service.feature(
        payload["layer_id"],
        int(payload["feature_id"]),
        encoding=payload.get("encoding", "wkb"),
    )
    return feature.to_wire()


def expressions_evaluate(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    service = ctx.features
    outcome = service.evaluate(
        payload["text"],
        layer_id=payload.get("layer_id"),
        feature_id=optional_int(payload.get("feature_id")),
    )
    return outcome.to_wire()


def expressions_validate(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    service = ctx.features
    return service.check(payload["text"], layer_id=payload.get("layer_id")).to_wire()


def editing_begin(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    service = ctx.features
    session = ctx.editing.begin(binding, service, payload["layer_id"])
    return {"session_id": session.id, "layer_id": session.layer_id}


def editing_add(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    session = ctx.editing.require(binding, payload["session_id"])
    feature_id = session.add(
        dict(payload["attributes"]),
        geometry(payload.get("geometry")),
    )
    return {"feature_id": feature_id, "pending": session.pending}


def editing_update(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    session = ctx.editing.require(binding, payload["session_id"])
    session.update(
        int(payload["feature_id"]),
        dict(payload["attributes"]) if payload.get("attributes") else None,
        geometry(payload.get("geometry")),
    )
    return {"session_id": session.id, "pending": session.pending}


def editing_delete(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    session = ctx.editing.require(binding, payload["session_id"])
    session.delete(int(payload["feature_id"]))
    return {"session_id": session.id, "pending": session.pending}


def editing_commit(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    session = ctx.editing.require(binding, payload["session_id"])
    return session.commit().to_wire()


def editing_rollback(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    session = ctx.editing.require(binding, payload["session_id"])
    session.rollback()
    return {"session_id": session.id, "pending": session.pending}


HANDLERS: dict[str, HostHandler] = {
    "blob.get": blob_get,
    "features.page": features_page,
    "features.get": features_get,
    "expressions.evaluate": expressions_evaluate,
    "expressions.validate": expressions_validate,
    "editing.begin": editing_begin,
    "editing.add": editing_add,
    "editing.update": editing_update,
    "editing.delete": editing_delete,
    "editing.commit": editing_commit,
    "editing.rollback": editing_rollback,
}
"""
Every declared id this module answers, and the function that answers it."""
