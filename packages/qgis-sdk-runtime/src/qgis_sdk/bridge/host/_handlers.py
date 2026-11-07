"""The handlers that answer each operation, the fetch stream and the registration."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import FileOperation, HostAuthority
from qgis_sdk.bridge.host._operations import HOST_OPERATIONS, HostOperation
from qgis_sdk.bridge.host._schemas import (
    BLOB_CHUNK_BYTES,
    DEFAULT_PAGE,
    MAX_FEATURE_PAGE,
    _page,
)
from qgis_sdk.bridge.host._services import HostServices
from qgis_sdk.bridge.protocol import BridgeOperation
from qgis_sdk.bridge.streams import StreamSink
from qgis_sdk.models import (
    DEFAULT_FEATURE_PAGE,
    AlgorithmInfo,
    CanvasExtent,
    CanvasPoint,
    FeatureQuery,
    FileRef,
    Geometry,
    LayoutSettings,
    NetworkRequest,
    ProjectChange,
    QgisSdkDecodeError,
    QgisSdkResponseTooLargeError,
    Response,
    RunResult,
    ZoomTarget,
    labelling_from_wire,
    layer_info,
    renderer_from_wire,
)
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkInvalidRequestError,
    QgisSdkUnknownHandleError,
)
from qgis_sdk.network.client import NetworkDefaults, build_request
from qgis_sdk.services.algorithms import Algorithms
from qgis_sdk.services.canvas import Canvas
from qgis_sdk.services.connections import Connections
from qgis_sdk.services.features import EditingSession, Features
from qgis_sdk.services.layouts import Layouts
from qgis_sdk.services.network import NetworkTransport
from qgis_sdk.services.project import Project
from qgis_sdk.services.rasters import Rasters

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import Dispatcher, ViewBinding


def _plain(value: Any) -> Any:
    """Unwrap a value DTO so the dispatcher's serialization check accepts it."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _wire(value: Any) -> Any:
    """Return a model's declared wire shape, falling back to a plain DTO.

    A renderer or a labelling has a ``to_wire`` for the same reason a layer
    description has one: what crosses the wire is a decision the model makes,
    not whatever ``asdict`` happens to flatten.
    """
    writer = getattr(value, "to_wire", None)
    return writer() if callable(writer) else _plain(value)


def _offset(cursor: Any) -> int:
    """Return the offset a cursor encodes; the request schema refused the rest."""
    return 0 if cursor is None else int(cursor)


def _page_of(items: Sequence[Any], payload: Mapping[str, Any]) -> dict:
    """Slice a sequence by the cursor a page sent back."""
    limit = payload.get("limit", DEFAULT_PAGE)
    start = _offset(payload.get("cursor"))
    window = list(items[start : start + limit])
    truncated = start + limit < len(items)
    return _page(
        [_plain(item) for item in window],
        str(start + limit) if truncated else None,
        truncated,
    )


BoundHostHandler = Callable[["ViewBinding", Mapping[str, Any]], Any]


def _handlers(
    services: HostServices, editing: EditingSessions
) -> dict[str, BoundHostHandler]:
    """Bind each operation id to the Protocol call and the shape it returns.

    Every handler receives the caller's binding; the ones that take a file ref
    hand it to the authority, which resolves the ref against that binding and
    never against anything in the payload. ``editing`` is the registry the
    lifecycle operations share, so a session one call began is the session the
    next call names - and the one disposal closes.
    """
    authority = services.authority

    def layers_list(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(
            [layer_info(info) for info in services.layers.list_layers()], payload
        )

    def layers_get(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return layer_info(services.layers.layer(payload["layer_id"]))

    def layers_open_vector(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(services.layers.open_vector(path))

    def layers_open_mesh(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(services.layers.open_mesh(path))

    def layers_open_point_cloud(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> Any:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(services.layers.open_point_cloud(path))

    def layers_open_vector_tile(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> Any:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(services.layers.open_vector_tile(path))

    def layers_open_annotation(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        # An annotation layer is created inside the project, so the request
        # carries the name it is created under rather than a file to read: a
        # page that could name a path here would be asking to open a file the
        # authority never resolved.
        return _plain(services.layers.open_annotation(str(payload["name"])))

    def layers_open_tiled_scene(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> Any:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(services.layers.open_tiled_scene(path))

    def files_export(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        written = authority.export_file(binding, payload["file"], payload["content"])
        return {"bytes_written": written, "name": str(payload["file"].get("name", ""))}

    def blob_get(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        offset = int(payload.get("offset", 0))
        length = int(payload.get("length", BLOB_CHUNK_BYTES))
        ref = authority.blob_info(binding, payload["blob"])
        chunk = authority.read_blob(
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

    def project_layer_ids(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(services.project.layer_ids(), payload)

    def settings_get(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return services.settings.get(payload["key"], payload.get("default"))

    def notifications_info(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        services.notifications.info(payload["message"])

    def styles_apply(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        services.styles.apply_style(payload["layer_id"], payload["style"])

    def symbology_get(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _wire(services.styles.symbology(payload["layer_id"]))

    def symbology_set(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        services.styles.set_symbology(
            payload["layer_id"], renderer_from_wire(payload["renderer"])
        )

    def labelling_get(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _wire(services.styles.labelling(payload["layer_id"]))

    def labelling_set(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        services.styles.set_labelling(
            payload["layer_id"], labelling_from_wire(payload["labelling"])
        )

    def styles_list(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(services.styles.list_styles(payload.get("kind")), payload)

    def styles_export(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _wire(
            services.styles.export_style(payload["layer_id"], payload["format"])
        )

    def styles_import(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        services.styles.import_style(
            payload["layer_id"], payload["text"], payload["format"]
        )

    def connections_list(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(_connections(services).list_connections(), payload)

    def connections_describe(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _wire(
            _connections(services).connection(
                payload["provider"], payload["connection"]
            )
        )

    def connections_browse(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(
            _connections(services).browse(
                payload["provider"], payload["connection"], payload.get("schema")
            ),
            payload,
        )

    def connections_open_layer(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _wire(
            _connections(services).open_layer(
                payload["provider"],
                payload["connection"],
                payload["schema"],
                payload["item"],
            )
        )

    def connections_test(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _wire(
            _connections(services).test(payload["provider"], payload["connection"])
        )

    def auth_configurations(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(_connections(services).auth_configurations(), payload)

    def auth_attach(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        _connections(services).attach_auth_config(
            payload["provider"], payload["connection"], payload["auth_config"]
        )

    def algorithms_providers(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(_algorithms(services).providers(), payload)

    def algorithms_list(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        found = _algorithms(services).list(payload.get("provider"))
        return _page_of([_summary(info) for info in found], payload)

    def algorithms_describe(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _algorithm_wire(_algorithms(services).describe(payload["algorithm_id"]))

    def algorithms_run(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        params = {
            str(name): _resolve_input(authority, binding, value)
            for name, value in payload["params"].items()
        }
        result = _algorithms(services).run(payload["algorithm_id"], params)
        return _result_for_view(services, binding, result)

    def algorithms_run_model(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        model = _plugin_file(
            services,
            authority.resolve_file(binding, payload["model"], FileOperation.READ),
        )
        params = {
            str(name): _resolve_input(authority, binding, value)
            for name, value in payload.get("params", {}).items()
        }
        result = _algorithms(services).run_model(model, params)
        return _result_for_view(services, binding, result)

    def algorithms_batch(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        results = []
        for item in payload["runs"]:
            params = {
                str(name): _resolve_input(authority, binding, value)
                for name, value in item.get("params", {}).items()
            }
            result = _algorithms(services).run(item["algorithm_id"], params)
            results.append(_result_for_view(services, binding, result))
        return {"results": results}

    def layouts_list(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _page_of(_layouts(services).list(), payload)

    def layouts_load_template(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(_layouts(services).load_template(_plugin_file(services, path)))

    def layouts_export(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        overwrite = bool(payload.get("overwrite", False))
        destination = None
        if payload.get("destination") is not None:
            path = authority.resolve_file(
                binding, payload["destination"], FileOperation.WRITE
            )
            destination = _plugin_file(
                services, path, writable=True, overwrite=overwrite
            )
        export = _layouts(services).render(
            payload["layout"],
            format=payload.get("format", "pdf"),
            destination=destination,
            settings=_layout_settings(payload),
            overwrite=overwrite,
        )
        return {
            "file": authority.grant_file(binding, export.path).to_wire(),
            "format": export.format,
            "pages": export.pages,
            "bytes": export.bytes,
        }

    def layouts_atlas(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        run = _layouts(services).render_atlas(
            payload["layout"],
            format=payload.get("format", "pdf"),
            pattern=payload.get("pattern"),
            settings=_layout_settings(payload),
            overwrite=bool(payload.get("overwrite", False)),
        )
        return {
            "directory": authority.grant_directory(binding, run.directory).to_wire(),
            "format": run.format,
            "pages": [
                {
                    "index": page.index,
                    "feature_id": page.feature_id,
                    "file": authority.grant_file(binding, page.path).to_wire(),
                }
                for page in run.pages
            ],
        }

    def network_fetch(binding: ViewBinding, payload: Mapping[str, Any]) -> _Fetch:
        grant = authority.require_network(binding)
        if services.network is None:
            raise QgisSdkBridgeError("this host has no network transport configured")
        return _Fetch(services.network, grant.constrain(_fetch_request(payload)))

    def features_page(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> Iterator[dict[str, Any]]:
        """Stream pages until the layer runs out, one bounded page per event.

        The pull shape is the point: the host asks the provider for one page,
        hands it to the view, and stops until the view pumps again. A page that
        stops early has cost the host one page, not the dataset.
        """
        service = _features(services)
        layer_id = payload["layer_id"]
        query = _feature_query(payload)

        def pages() -> Iterator[dict[str, Any]]:
            cursor = query.cursor
            while True:
                page = service.page(layer_id, replace(query, cursor=cursor))
                yield page.to_wire()
                if not page.truncated or page.next_cursor is None:
                    return
                cursor = page.next_cursor

        return pages()

    def features_get(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        service = _features(services)
        feature = service.feature(
            payload["layer_id"],
            int(payload["feature_id"]),
            encoding=payload.get("encoding", "wkb"),
        )
        return feature.to_wire()

    def expressions_evaluate(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        service = _features(services)
        outcome = service.evaluate(
            payload["text"],
            layer_id=payload.get("layer_id"),
            feature_id=_optional_int(payload.get("feature_id")),
        )
        return outcome.to_wire()

    def expressions_validate(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        service = _features(services)
        return service.check(
            payload["text"], layer_id=payload.get("layer_id")
        ).to_wire()

    def editing_begin(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        service = _features(services)
        session = editing.begin(binding, service, payload["layer_id"])
        return {"session_id": session.id, "layer_id": session.layer_id}

    def editing_add(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        session = editing.require(binding, payload["session_id"])
        feature_id = session.add(
            dict(payload["attributes"]),
            _geometry(payload.get("geometry")),
        )
        return {"feature_id": feature_id, "pending": session.pending}

    def editing_update(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        session = editing.require(binding, payload["session_id"])
        session.update(
            int(payload["feature_id"]),
            dict(payload["attributes"]) if payload.get("attributes") else None,
            _geometry(payload.get("geometry")),
        )
        return {"session_id": session.id, "pending": session.pending}

    def editing_delete(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        session = editing.require(binding, payload["session_id"])
        session.delete(int(payload["feature_id"]))
        return {"session_id": session.id, "pending": session.pending}

    def editing_commit(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        session = editing.require(binding, payload["session_id"])
        return session.commit().to_wire()

    def editing_rollback(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        session = editing.require(binding, payload["session_id"])
        session.rollback()
        return {"session_id": session.id, "pending": session.pending}

    def canvas_extent(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _canvas(services).extent().to_wire()

    def canvas_scale(binding: ViewBinding, payload: Mapping[str, Any]) -> float:
        return _canvas(services).scale()

    def canvas_crs(binding: ViewBinding, payload: Mapping[str, Any]) -> str | None:
        return _canvas(services).crs()

    def canvas_center(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _canvas(services).center().to_wire()

    def canvas_zoom_to(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        target = ZoomTarget.from_wire(payload)
        return _canvas(services).zoom_to(target).to_wire()

    def canvas_refresh(binding: ViewBinding, payload: Mapping[str, Any]) -> None:
        _canvas(services).refresh()

    def canvas_themes(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _canvas(services).themes().to_wire()

    def canvas_apply_theme(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _canvas(services).apply_theme(payload["name"]).to_wire()

    def canvas_extent_changed(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> _WatchExtent:
        return _WatchExtent(_canvas(services))

    def canvas_capture(binding: ViewBinding, payload: Mapping[str, Any]) -> _Capture:
        return _Capture(_canvas(services), payload["shape"])

    def rasters_open(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _rasters(services).open_raster(path).to_wire()

    def rasters_get(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _rasters(services).raster(payload["layer_id"]).to_wire()

    def rasters_statistics(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return (
            _rasters(services)
            .statistics(payload["layer_id"], int(payload["band"]))
            .to_wire()
        )

    def rasters_sample(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return (
            _rasters(services)
            .sample(
                payload["layer_id"],
                CanvasPoint.from_wire(payload["point"]),
                band=_optional_int(payload.get("band")),
            )
            .to_wire()
        )

    def project_tree(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _project(services).layer_tree().to_wire()

    def project_add_layer(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return (
            _project(services)
            .add_layer(payload["layer_id"], group=payload.get("group"))
            .to_wire()
        )

    def project_remove_layer(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _project(services).remove_layer(payload["layer_id"]).to_wire()

    def project_move_layer(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return (
            _project(services)
            .move_layer(
                payload["layer_id"],
                group=payload.get("group"),
                index=_optional_int(payload.get("index")),
            )
            .to_wire()
        )

    def project_set_visible(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return (
            _project(services)
            .set_visible(payload["node_id"], bool(payload["visible"]))
            .to_wire()
        )

    def project_crs(binding: ViewBinding, payload: Mapping[str, Any]) -> str | None:
        return _project(services).crs()

    def project_set_crs(binding: ViewBinding, payload: Mapping[str, Any]) -> str:
        return _project(services).set_crs(payload["auth_id"])

    def project_variables(binding: ViewBinding, payload: Mapping[str, Any]) -> list:
        return [entry.to_wire() for entry in _project(services).variables()]

    def project_set_variable(binding: ViewBinding, payload: Mapping[str, Any]) -> list:
        return [
            entry.to_wire()
            for entry in _project(services).set_variable(
                payload["name"], payload["value"]
            )
        ]

    def project_unset_variable(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> list:
        return [
            entry.to_wire()
            for entry in _project(services).unset_variable(payload["name"])
        ]

    def project_properties(binding: ViewBinding, payload: Mapping[str, Any]) -> list:
        return [entry.to_wire() for entry in _project(services).custom_properties()]

    def project_set_property(binding: ViewBinding, payload: Mapping[str, Any]) -> list:
        return [
            entry.to_wire()
            for entry in _project(services).set_custom_property(
                payload["name"], payload["value"]
            )
        ]

    def project_unset_property(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> list:
        return [
            entry.to_wire()
            for entry in _project(services).unset_custom_property(payload["name"])
        ]

    def project_bookmarks(binding: ViewBinding, payload: Mapping[str, Any]) -> list:
        return [bookmark.to_wire() for bookmark in _project(services).bookmarks()]

    def project_bookmark(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _project(services).bookmark(payload["name"]).to_wire()

    def project_add_bookmark(binding: ViewBinding, payload: Mapping[str, Any]) -> list:
        return [
            bookmark.to_wire()
            for bookmark in _project(services).add_bookmark(
                payload["name"], CanvasExtent.from_wire(payload["extent"])
            )
        ]

    def project_remove_bookmark(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> list:
        return [
            bookmark.to_wire()
            for bookmark in _project(services).remove_bookmark(payload["name"])
        ]

    def project_read(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _project(services).read(path).to_wire()

    def project_write(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        path = authority.resolve_file(binding, payload["file"], FileOperation.WRITE)
        return (
            _project(services)
            .write(path, overwrite=bool(payload.get("overwrite", False)))
            .to_wire()
        )

    def project_save(binding: ViewBinding, payload: Mapping[str, Any]) -> dict:
        return _project(services).save().to_wire()

    def project_changed(
        binding: ViewBinding, payload: Mapping[str, Any]
    ) -> _WatchProject:
        return _WatchProject(_project(services))

    return {
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
        "connections.list": connections_list,
        "connections.describe": connections_describe,
        "connections.browse": connections_browse,
        "connections.open_layer": connections_open_layer,
        "connections.test": connections_test,
        "auth.configurations": auth_configurations,
        "auth.attach": auth_attach,
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
        "network.fetch": network_fetch,
    }


def _layouts(services: HostServices) -> Layouts:
    if services.layouts is None:
        raise QgisSdkBridgeError("this host has no layouts service configured")
    return services.layouts


def _connections(services: HostServices) -> Connections:
    if services.connections is None:
        raise QgisSdkBridgeError("this host has no connections service configured")
    return services.connections


def _plugin_file(
    services: HostServices,
    path: Any,
    *,
    writable: bool = False,
    overwrite: bool = False,
) -> FileRef:
    """Re-mint one of the view's paths as a ref the plugin's files service holds.

    The view's ref names a path *for the view*; a service on this side of the
    seam resolves refs through the plugin's files service, so a path has to
    cross as the plugin's own ref - and it is refused here when the plugin has
    no files service, never quietly turned back into a string (decision-20: a
    path is not authority, on either side of the bridge).
    """
    files = services.files
    if files is None:
        raise QgisSdkBridgeError(
            "this host has no files service to hand a plugin-side ref out"
        )
    # A destination need not exist yet, and a read grant insists it does; a
    # write grant is the one an export destination can carry.
    operations: tuple[str, ...] = ("write",) if writable else ("read",)
    return files.grant_file(path, operations=operations, overwrite=overwrite)


def _layout_settings(payload: Mapping[str, Any]) -> LayoutSettings:
    """Build the render settings a page declared, defaulting what it left out."""
    return LayoutSettings(
        dpi=int(payload.get("dpi", LayoutSettings().dpi)),
        rasterize=bool(payload.get("rasterize", False)),
        georeference=bool(payload.get("georeference", False)),
    )


def _rasters(services: HostServices) -> Rasters:
    if services.rasters is None:
        raise QgisSdkBridgeError("this host has no raster service configured")
    return services.rasters


def _project(services: HostServices) -> Project:
    if services.project is None:  # pragma: no cover - a required field
        raise QgisSdkBridgeError("this host has no project service configured")
    return services.project


class _WatchProject:
    """The push source behind ``project.changed``.

    The project calls back whenever it changes, and the sink turns each frame
    into one ``data`` event; the frames are the project's own order, which is
    the order a page re-reads in. Disposal before the first change cancels the
    subscription, so a closed page leaves no listener behind.
    """

    def __init__(self, project: Project) -> None:
        self._project = project
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        def deliver(change: ProjectChange) -> None:
            sink.emit(change.to_wire())

        # The stream does not complete: a page follows the project until it
        # unsubscribes, so only disposal or an error ends it.
        self._cancel = self._project.watch_changes(deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


def _algorithms(services: HostServices) -> Algorithms:
    if services.algorithms is None:
        raise QgisSdkBridgeError("this host has no algorithms service configured")
    return services.algorithms


def _summary(info: AlgorithmInfo) -> dict[str, Any]:
    return {
        "id": info.id,
        "provider": info.provider,
        "name": info.name,
        "label": info.label,
        "group": info.group,
        "deprecated": info.deprecated,
    }


def _algorithm_wire(info: AlgorithmInfo) -> dict[str, Any]:
    """Spell one description with every declared field present.

    A page validates the reply against the generated type, so nothing is left
    to a default the page cannot see.
    """
    parameters = []
    for parameter in info.parameters:
        has_default = (
            parameter.has_default
            if parameter.has_default is not None
            else parameter.default is not None
        )
        parameters.append(
            {
                "name": parameter.name,
                "kind": parameter.kind,
                "label": parameter.label,
                "description": parameter.description,
                "optional": parameter.optional,
                "advanced": parameter.advanced,
                "hidden": parameter.hidden,
                "destination": parameter.destination,
                "required": parameter.required,
                "default_json": json.dumps(parameter.default) if has_default else None,
                "options": list(parameter.options),
                "multiple": parameter.multiple,
                "number_type": parameter.number_type,
                "minimum": parameter.minimum,
                "maximum": parameter.maximum,
                "extension": parameter.extension,
            }
        )
    return {
        **_summary(info),
        "group_id": info.group_id,
        "help": info.help,
        "parameters": parameters,
        "outputs": [
            {"name": output.name, "kind": output.kind, "label": output.label}
            for output in info.outputs
        ],
    }


def _resolve_input(authority: HostAuthority, binding: ViewBinding, value: Any) -> Any:
    """Turn a ref the view holds into the path the algorithm reads.

    Only a ref-shaped value is touched; the authority resolves it against the
    calling view, so a ref minted for another view or a forged id is refused
    here before the algorithm sees a parameter. Everything else (a layer id,
    a number, a list) crosses as the page sent it.
    """
    if isinstance(value, Mapping) and value.get("kind") in ("file", "directory"):
        return str(authority.resolve_file(binding, value, FileOperation.READ))
    return value


def _result_for_view(
    services: HostServices, binding: ViewBinding, result: RunResult
) -> dict[str, Any]:
    """Re-mint the refs a run produced so the calling view holds them, not the plugin."""
    outputs: dict[str, object] = {}
    for name, value in result.outputs.items():
        if isinstance(value, FileRef):
            if services.files is None:
                raise QgisSdkBridgeError(
                    "this host has no files service to hand a run's file outputs over"
                )
            path = services.files.resolve(value)
            if value.kind == "directory":
                value = services.authority.grant_directory(binding, path)
            else:
                value = services.authority.grant_file(binding, path)
        outputs[name] = value
    return RunResult(algorithm=result.algorithm, outputs=outputs).to_wire()


def _fetch_request(payload: Mapping[str, Any]) -> NetworkRequest:
    """Turn the declared fetch payload into the request the grant constrains.

    The client's own validation applies (absolute http(s) URL, no user-info);
    the ceilings come from the grant afterwards, so a view asking for more
    gets the grant's limits and one asking for less keeps its own.
    """
    headers = {
        str(item["name"]): str(item["value"]) for item in payload.get("headers", [])
    }
    request = build_request(
        NetworkDefaults(),
        str(payload.get("method", "GET")),
        str(payload["url"]),
        data=payload.get("body"),
        headers=headers,
        timeout=payload.get("timeout_seconds"),
    )
    auth_config = payload.get("auth_config")
    if auth_config is not None:
        request = replace(request, auth_config=str(auth_config))
    return request


def _response_event(response: Response) -> dict[str, Any]:
    text: str | None
    encoded: str | None
    try:
        text, encoded = response.text, None
    except QgisSdkDecodeError:
        text, encoded = None, base64.b64encode(response.content).decode("ascii")
    return {
        "url": response.url,
        "status_code": response.status_code,
        "reason": response.reason,
        "headers": [{"name": n, "value": v} for n, v in response.headers.items()],
        "text": text,
        "base64": encoded,
    }


def _canvas(services: HostServices) -> Canvas:
    if services.canvas is None:
        raise QgisSdkBridgeError("this host has no map canvas configured")
    return services.canvas


class _WatchExtent:
    """The push source behind ``canvas.extent_changed``.

    The canvas calls back whenever the user moves it, and the sink turns each
    extent into one ``data`` frame; the frames are the canvas's order, which is
    the order a page draws them in. Disposal before the first pan cancels the
    subscription on the canvas, so a closed page leaves no listener behind.
    """

    def __init__(self, canvas: Canvas) -> None:
        self._canvas = canvas
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        def deliver(extent: CanvasExtent) -> None:
            sink.emit(extent.to_wire())

        # The stream does not complete: a page follows the map until it
        # unsubscribes, so only disposal or an error ends it.
        self._cancel = self._canvas.watch_extent(deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


class _Capture:
    """The push source behind ``canvas.capture``: one drawing, one geometry.

    The tool takes as long as the user takes, so the frame arrives on a later
    event loop turn and the subscription completes as soon as it does. A
    cancelled drawing - Escape, or a view that went away - ends the subscription
    as cancelled; either way the map tool is removed by the canceller.
    """

    def __init__(self, canvas: Canvas, shape: str) -> None:
        self._canvas = canvas
        self._shape = shape
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        def deliver(geometry: Geometry) -> None:
            self._done = True
            if sink.emit(geometry.to_wire()):
                sink.complete()

        self._cancel = self._canvas.capture(self._shape, deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


def _features(services: HostServices) -> Features:
    if services.features is None:
        raise QgisSdkBridgeError("this host has no features service configured")
    return services.features


def _feature_query(payload: Mapping[str, Any]) -> FeatureQuery:
    """Turn a wire request into the bounded query the service takes.

    The bounds are checked here, by name, rather than left to the layer: a page
    asking for more than ``MAX_FEATURE_PAGE`` features or a bbox that is not
    four numbers is a mistake in the request, and the caller hears which.
    """
    raw_bbox = payload.get("bbox")
    raw_ids = payload.get("ids")
    limit = int(payload.get("limit", DEFAULT_FEATURE_PAGE))
    if limit > MAX_FEATURE_PAGE:
        raise QgisSdkInvalidRequestError(
            f"limit is at most {MAX_FEATURE_PAGE} features, not {limit}"
        )
    bbox = None
    if raw_bbox is not None:
        if len(raw_bbox) != 4:
            raise QgisSdkInvalidRequestError(
                f"bbox is (min_x, min_y, max_x, max_y), not {len(raw_bbox)} numbers"
            )
        bbox = tuple(float(item) for item in raw_bbox)
    return FeatureQuery(
        limit=limit,
        cursor=payload.get("cursor"),
        expression=payload.get("expression"),
        bbox=bbox,
        ids=None if raw_ids is None else tuple(int(item) for item in raw_ids),
        encoding=payload.get("encoding", "wkb"),
        with_geometry=bool(payload.get("with_geometry", True)),
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _geometry(value: Any) -> Geometry | None:
    """Read a geometry a page sent back, or ``None`` when it sent none."""
    return None if value is None else Geometry.from_wire(value)


class EditingSessions:
    """The host's editing sessions, scoped to the view that opened them.

    A session is a buffer over a layer, so it is neither the service's nor the
    page's: it belongs to the view. Every session records its view, a call names
    its session id, and the dispatcher disposes what a closing view held, so a
    page that disappears mid-edit cannot leave a buffer open. Two views editing
    one layer are two sessions over one provider buffer, which the service is
    free to refuse - the host does not pretend otherwise.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, EditingSession]] = {}

    def begin(
        self, binding: ViewBinding, service: Features, layer_id: str
    ) -> EditingSession:
        session = service.begin_edit(layer_id)
        self._sessions[session.id] = (binding.view_id, session)
        return session

    def require(self, binding: ViewBinding, session_id: str) -> EditingSession:
        entry = self._sessions.get(session_id)
        if entry is None or entry[0] != binding.view_id:
            # A session begun by another view is reported exactly like one that
            # never existed: the reply must not become an oracle for other views.
            raise QgisSdkUnknownHandleError(
                f"editing session {session_id!r} is not open for this view"
            )
        return entry[1]

    def close(self, session_id: str) -> bool:
        entry = self._sessions.pop(session_id, None)
        if entry is None:
            return False
        entry[1].close()
        return True

    def close_view(self, view_id: str) -> None:
        for session_id, (owner, _session) in list(self._sessions.items()):
            if owner == view_id:
                self.close(session_id)


class _Fetch:
    """The push source behind ``network.fetch``: one request, one event, done.

    The transport delivers on a later event-loop turn; the sink wakes the
    view's channel. Disposal before delivery cancels the request, and a reply
    that lands after disposal writes into a closed sink, which is nothing.
    """

    def __init__(self, transport: NetworkTransport, request: NetworkRequest) -> None:
        self._transport = transport
        self._request = request
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        request = self._request

        def deliver(outcome: Response | Exception) -> None:
            self._done = True
            if isinstance(outcome, Response):
                if len(outcome.content) > request.max_body_bytes:
                    sink.fail(
                        QgisSdkResponseTooLargeError(
                            request.max_body_bytes,
                            method=request.method,
                            url=outcome.url,
                        )
                    )
                    return
                if sink.emit(_response_event(outcome)):
                    sink.complete()
                return
            sink.fail(outcome)

        self._cancel = self._transport.send(request, deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


def register_host_operations(
    dispatcher: Dispatcher,
    services: HostServices,
    *,
    only: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Register the curated operations on ``dispatcher`` and return their ids.

    ``only`` narrows the surface to a subset, which is how an application with a
    grant model hides what a view may not use instead of refusing it later. The
    ids that were registered are also the ids the handshake advertises, because
    the handshake reads the allowlist.

    Both failures happen before anything is registered. ``only`` is an
    authority-bearing argument, so an id it names that this module does not
    declare is a typo that would otherwise narrow the surface in silence; and a
    conflict with what the dispatcher already carries would otherwise leave the
    operations registered before it in place, on a call whose caller was told it
    failed.
    """
    editing = EditingSessions()
    handlers = _handlers(services, editing)
    wanted = _selected(only)
    operations = [
        BridgeOperation(
            id=operation.id,
            title=operation.title,
            request=operation.request,
            result=operation.result,
            events=operation.events,
        )
        for operation in wanted
    ]
    taken = {operation.id for operation in dispatcher.operations()}
    conflicts = [operation.id for operation in operations if operation.id in taken]
    if conflicts:
        raise QgisSdkBridgeError(
            f"duplicate operation id {conflicts[0]!r}; nothing was registered"
        )
    dispatcher.register_editing(close=editing.close, close_view=editing.close_view)
    streams = {operation.id for operation in wanted if operation.events is not None}
    for operation in operations:
        if operation.id in streams:
            dispatcher.register_bound_stream(operation, handlers[operation.id])
        else:
            dispatcher.register_bound(operation, handlers[operation.id])
    return tuple(operation.id for operation in operations)


def _selected(only: Sequence[str] | None) -> tuple[HostOperation, ...]:
    """Return the declared operations ``only`` names, refusing ids that are not declared."""
    if only is None:
        return HOST_OPERATIONS
    requested = set(only)
    declared = {operation.id for operation in HOST_OPERATIONS}
    unknown = sorted(requested - declared)
    if unknown:
        raise QgisSdkBridgeError(
            f"unknown host operation(s): {', '.join(unknown)}; "
            f"declared ids are {', '.join(sorted(declared))}"
        )
    return tuple(
        operation for operation in HOST_OPERATIONS if operation.id in requested
    )
