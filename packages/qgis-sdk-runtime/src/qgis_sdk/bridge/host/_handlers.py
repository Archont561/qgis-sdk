"""The handlers that answer each operation, the fetch stream and the registration."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import FileOperation, HostAuthority
from qgis_sdk.bridge.host._operations import HOST_OPERATIONS, HostOperation
from qgis_sdk.bridge.host._schemas import DEFAULT_PAGE, _page
from qgis_sdk.bridge.host._services import HostServices
from qgis_sdk.bridge.protocol import BridgeOperation
from qgis_sdk.bridge.streams import StreamSink
from qgis_sdk.models import (
    AlgorithmInfo,
    FileRef,
    NetworkRequest,
    QgisSdkDecodeError,
    QgisSdkResponseTooLargeError,
    Response,
    RunResult,
)
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.network.client import NetworkDefaults, build_request
from qgis_sdk.services.algorithms import Algorithms
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


def _handlers(services: HostServices) -> dict[str, BoundHostHandler]:
    """Bind each operation id to the Protocol call and the shape it returns.

    Every handler receives the caller's binding; the ones that take a file ref
    hand it to the authority, which resolves the ref against that binding and
    never against anything in the payload.
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

    return {
        "layers.list": layers_list,
        "layers.get": layers_get,
        "layers.open_vector": layers_open_vector,
        "files.export": files_export,
        "project.layer_ids": project_layer_ids,
        "settings.get": settings_get,
        "notifications.info": notifications_info,
        "styles.apply": styles_apply,
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
    handlers = _handlers(services)
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
