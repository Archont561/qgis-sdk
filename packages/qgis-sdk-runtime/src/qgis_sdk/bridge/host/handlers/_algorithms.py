"""Algorithms, models, batches and the layouts that print them."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import FileOperation
from qgis_sdk.bridge.host._context import Host, HostHandler
from qgis_sdk.bridge.host._support import (
    _plain,
    _summary,
    algorithm_wire,
    layout_settings,
    page_of,
    resolve_input,
    result_for_view,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def algorithms_providers(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return page_of(ctx.algorithms.providers(), payload)


def algorithms_list(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    found = ctx.algorithms.list(payload.get("provider"))
    return page_of([_summary(info) for info in found], payload)


def algorithms_describe(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    return algorithm_wire(ctx.algorithms.describe(payload["algorithm_id"]))


def algorithms_run(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    params = {
        str(name): resolve_input(ctx.authority, binding, value)
        for name, value in payload["params"].items()
    }
    result = ctx.algorithms.run(payload["algorithm_id"], params)
    return result_for_view(ctx.services, binding, result)


def algorithms_run_model(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    model = ctx.plugin_file(
        ctx.authority.resolve_file(binding, payload["model"], FileOperation.READ),
    )
    params = {
        str(name): resolve_input(ctx.authority, binding, value)
        for name, value in payload.get("params", {}).items()
    }
    result = ctx.algorithms.run_model(model, params)
    return result_for_view(ctx.services, binding, result)


def algorithms_batch(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    results = []
    for item in payload["runs"]:
        params = {
            str(name): resolve_input(ctx.authority, binding, value)
            for name, value in item.get("params", {}).items()
        }
        result = ctx.algorithms.run(item["algorithm_id"], params)
        results.append(result_for_view(ctx.services, binding, result))
    return {"results": results}


def layouts_list(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    return page_of(ctx.layouts.list(), payload)


def layouts_load_template(
    ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]
) -> dict:
    path = ctx.authority.resolve_file(binding, payload["file"], FileOperation.READ)
    return _plain(ctx.layouts.load_template(ctx.plugin_file(path)))


def layouts_export(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    overwrite = bool(payload.get("overwrite", False))
    destination = None
    if payload.get("destination") is not None:
        path = ctx.authority.resolve_file(
            binding, payload["destination"], FileOperation.WRITE
        )
        destination = ctx.plugin_file(path, writable=True, overwrite=overwrite)
    export = ctx.layouts.render(
        payload["layout"],
        format=payload.get("format", "pdf"),
        destination=destination,
        settings=layout_settings(payload),
        overwrite=overwrite,
    )
    return {
        "file": ctx.authority.grant_file(binding, export.path).to_wire(),
        "format": export.format,
        "pages": export.pages,
        "bytes": export.bytes,
    }


def layouts_atlas(ctx: Host, binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
    run = ctx.layouts.render_atlas(
        payload["layout"],
        format=payload.get("format", "pdf"),
        pattern=payload.get("pattern"),
        settings=layout_settings(payload),
        overwrite=bool(payload.get("overwrite", False)),
    )
    return {
        "directory": ctx.authority.grant_directory(binding, run.directory).to_wire(),
        "format": run.format,
        "pages": [
            {
                "index": page.index,
                "feature_id": page.feature_id,
                "file": ctx.authority.grant_file(binding, page.path).to_wire(),
            }
            for page in run.pages
        ],
    }


HANDLERS: dict[str, HostHandler] = {
    "algorithms.providers": algorithms_providers,
    "algorithms.list": algorithms_list,
    "algorithms.describe": algorithms_describe,
    "layouts.list": layouts_list,
    "layouts.load_template": layouts_load_template,
    "layouts.export": layouts_export,
    "layouts.atlas": layouts_atlas,
    "algorithms.run": algorithms_run,
    "algorithms.run_model": algorithms_run_model,
    "algorithms.batch": algorithms_batch,
}
"""
Every declared id this module answers, and the function that answers it."""
