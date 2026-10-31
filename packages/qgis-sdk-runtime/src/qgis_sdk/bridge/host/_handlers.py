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
    FeatureQuery,
    FileRef,
    Geometry,
    NetworkRequest,
    QgisSdkDecodeError,
    QgisSdkResponseTooLargeError,
    Response,
    RunResult,
)
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkInvalidRequestError,
    QgisSdkUnknownHandleError,
)
from qgis_sdk.network.client import NetworkDefaults, build_request
from qgis_sdk.services.algorithms import Algorithms
from qgis_sdk.services.features import EditingSession, Features
from qgis_sdk.services.network import NetworkTransport

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import Dispatcher, ViewBinding


def _plain(value: Any) -> Any:
    """Unwrap a value DTO so the dispatcher's serialization check accepts it."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


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
        return _page_of(services.layers.list_layers(), payload)

    def layers_get(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        return _plain(services.layers.layer(payload["layer_id"]))

    def layers_open_vector(binding: ViewBinding, payload: Mapping[str, Any]) -> Any:
        path = authority.resolve_file(binding, payload["file"], FileOperation.READ)
        return _plain(services.layers.open_vector(path))

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

    return {
        "layers.list": layers_list,
        "layers.get": layers_get,
        "layers.open_vector": layers_open_vector,
        "files.export": files_export,
        "project.layer_ids": project_layer_ids,
        "settings.get": settings_get,
        "notifications.info": notifications_info,
        "styles.apply": styles_apply,
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
        "algorithms.run": algorithms_run,
        "network.fetch": network_fetch,
    }


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
