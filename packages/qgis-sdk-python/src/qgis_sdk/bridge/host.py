"""The curated host surface a web view may call, and the wiring that answers it.

Decision-27 draws the line this module implements: a page may reach the five
curated Protocols in :mod:`qgis_sdk.services` - and nothing else of the QGIS API.
What a page gets is not "the host": it is a declared list of operations, each
with a request and a result schema, a canonical grant, a thread affinity and the
Protocol method it wraps. The same list is what the TypeScript module in
``@archont561/qgis-sdk/host`` is generated from, so the surface a page
sees cannot drift from the surface the host answers.

Two rules are enforced by the declaration rather than by review:

* **Deferred is a recorded decision.** Every method of a curated Protocol is
  either one of :data:`HOST_OPERATIONS` or one of
  :data:`DEFERRED_HOST_METHODS` with the reason it is absent. A test reflects
  the Protocols and fails when a method appears in neither, so adding a Protocol
  method cannot quietly become an unreachable - or, worse, an unintentionally
  reachable - part of the wire surface.
* **No page-supplied paths, no unbounded arrays.** Nothing here takes a
  filesystem path: ``layers.open_vector`` and ``files.export`` take a
  host-minted ``FileRef`` (:mod:`qgis_sdk.bridge.authority`) that is resolved
  against the calling view, and every list that can grow is paged by
  :func:`_page` before it crosses ``QWebChannel``.
* **Nothing slow is a call.** ``network.fetch`` is a stream: the request goes
  out through the view's network grant and the reply arrives as one event on
  a later event-loop turn, so the GUI thread never waits on a socket.

Beyond the read-only operations and ``styles.apply``, the surface carries the
TASK-20 slice: an open through a file ref, an export through a file ref, and a
fetch through a network grant. Each is refused with its own code when the ref
or grant does not cover what was asked (decision-20).
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from typing import TYPE_CHECKING, Any

from qgis_sdk.core import PluginContext
from qgis_sdk.models import (
    NetworkRequest,
    QgisSdkDecodeError,
    QgisSdkResponseTooLargeError,
    Response,
)
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.network.client import NetworkDefaults, build_request
from qgis_sdk.services.contracts import Notifications
from qgis_sdk.services.layers import Layers
from qgis_sdk.services.network import NetworkTransport
from qgis_sdk.services.project import Project
from qgis_sdk.services.settings import Settings
from qgis_sdk.services.styles import Styles

from .authority import FILE_REF, FileOperation, HostAuthority
from .protocol import HOST_SCHEMA_VERSION, BridgeOperation
from .streams import StreamSink

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from .dispatch import Dispatcher, ViewBinding

__all__ = [
    "DEFAULT_PAGE",
    "DEFERRED_HOST_METHODS",
    "HOST_OPERATIONS",
    "MAX_PAGE",
    "HostOperation",
    "HostServices",
    "host_description",
    "host_grants",
    "register_host_operations",
]

#: Rows a page gets when it does not ask for a size.
DEFAULT_PAGE = 50

#: Ceiling for one page: a page that asks for a million rows gets fifty.
MAX_PAGE = 200

GUI = "gui"
WORKER = "worker"


def _object(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


def _array(items: Mapping[str, Any]) -> dict:
    return {"type": "array", "items": items}


#: One schema object, reused by every operation that returns a layer, so the
#: generated module names it once and both a get and a page item share the type.
VECTOR_LAYER_INFO = _object(
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "geometry_type": {"enum": ["point", "line", "polygon", "none"]},
        "field_names": _array({"type": "string"}),
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    required=("id", "name", "geometry_type", "field_names", "crs"),
)

#: The paging request, also shared: a page size and a cursor. The cursor is the
#: offset this module issued in ``next_cursor``, encoded as a decimal string, so
#: the declared pattern refuses anything else before a handler runs - reading a
#: malformed cursor as "start over" would restart the first page in silence.
PAGE_REQUEST = _object(
    {
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE},
        "cursor": {"type": "string", "pattern": "[0-9]+"},
    }
)

_NOTHING = {"type": "null"}
_TEXT_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}

#: One HTTP header, as a name/value pair: a list of these is a wire shape every
#: generator can type, where a free-form map is not.
HTTP_HEADER = _object(
    {"name": {"type": "string"}, "value": {"type": "string"}},
    required=("name", "value"),
)
HTTP_HEADER["title"] = "HttpHeader"

FETCH_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
MAX_FETCH_TIMEOUT_SECONDS = 300

#: What a view may say about a request. The URL is absolute; the view's grant
#: decides whether its origin, the method and the authentication are allowed,
#: and the host's limits cap the body and the redirects whatever is asked.
FETCH_REQUEST = _object(
    {
        "url": {"type": "string"},
        "method": {"enum": list(FETCH_METHODS)},
        "headers": _array(HTTP_HEADER),
        "body": {"type": "string"},
        "timeout_seconds": {
            "type": "number",
            "minimum": 0.1,
            "maximum": MAX_FETCH_TIMEOUT_SECONDS,
        },
        "auth_config": {"type": "string"},
    },
    required=("url",),
)

#: The one event a fetch emits. ``text`` is the body decoded with its declared
#: charset (UTF-8 when none); a body that is not text crosses as ``base64``.
FETCH_RESPONSE = _object(
    {
        "url": {"type": "string"},
        "status_code": {"type": "integer"},
        "reason": {"type": "string"},
        "headers": _array(HTTP_HEADER),
        "text": _TEXT_OR_NULL,
        "base64": _TEXT_OR_NULL,
    },
    required=("url", "status_code", "reason", "headers", "text", "base64"),
)


def _page(items: Sequence[Any], cursor: str | None, truncated: bool) -> dict:
    """Shape one page, with the cursor only when something is left."""
    page: dict[str, Any] = {"items": list(items), "truncated": truncated}
    if truncated:
        page["next_cursor"] = cursor
    return page


def _page_result(items: Mapping[str, Any]) -> dict:
    return _object(
        {
            "items": _array(items),
            "truncated": {"type": "boolean"},
            "next_cursor": {"type": "string"},
        },
        required=("items", "truncated"),
    )


@dataclass(frozen=True, slots=True)
class HostOperation:
    """One operation of the host surface, declared rather than inferred.

    ``source`` names the Protocol method it wraps so a test can prove the two
    lists stay in step, and ``grant`` is the canonical permission an application
    checks - a namespace-wide flag would grant every future method at once.
    """

    id: str
    title: str
    source: str
    grant: str
    affinity: str
    request: Mapping[str, Any]
    result: Mapping[str, Any] | None = None
    events: Mapping[str, Mapping[str, Any]] | None = None
    request_name: str | None = None
    result_name: str | None = None

    def to_description(self) -> dict[str, Any]:
        """Return the action- or stream-shaped record the generator understands."""
        described: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "handler": self.id,
            "request": self.request,
        }
        if self.events is not None:
            described["events"] = {kind: schema for kind, schema in self.events.items()}
        else:
            described["result"] = self.result
        if self.request_name is not None:
            described["request_name"] = self.request_name
        if self.result_name is not None:
            described["result_name"] = self.result_name
        return described


HOST_OPERATIONS: tuple[HostOperation, ...] = (
    HostOperation(
        id="layers.list",
        title="List the layers this runtime opened",
        source="Layers.list_layers",
        grant="layers.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=_page_result(VECTOR_LAYER_INFO),
        request_name="PageRequest",
        result_name="LayerPage",
    ),
    HostOperation(
        id="layers.get",
        title="Describe one opened layer",
        source="Layers.layer",
        grant="layers.read",
        affinity=GUI,
        request=_object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=VECTOR_LAYER_INFO,
        request_name="LayerRequest",
        result_name="VectorLayerInfo",
    ),
    HostOperation(
        id="project.layer_ids",
        title="List the project's layer ids in project order",
        source="Project.layer_ids",
        grant="project.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=_page_result({"type": "string"}),
        result_name="IdPage",
    ),
    HostOperation(
        id="settings.get",
        title="Read one setting owned by this runtime",
        source="Settings.get",
        grant="settings.read",
        affinity=GUI,
        request=_object(
            {
                "key": {"type": "string"},
                "default": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            required=("key",),
        ),
        result={"anyOf": [{"type": "string"}, {"type": "null"}]},
    ),
    HostOperation(
        id="notifications.info",
        title="Publish an informational message",
        source="Notifications.info",
        grant="notifications.info",
        affinity=GUI,
        request=_object({"message": {"type": "string"}}, required=("message",)),
        result=_NOTHING,
    ),
    HostOperation(
        id="styles.apply",
        title="Apply one packaged style to an owned layer",
        source="Styles.apply_style",
        grant="styles.apply",
        affinity=GUI,
        request=_object(
            {"layer_id": {"type": "string"}, "style": {"type": "string"}},
            required=("layer_id", "style"),
        ),
        result=_NOTHING,
    ),
    HostOperation(
        id="layers.open_vector",
        title="Open the vector dataset a file ref names",
        source="Layers.open_vector",
        grant="layers.open",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=VECTOR_LAYER_INFO,
        request_name="OpenVectorRequest",
        result_name="VectorLayerInfo",
    ),
    HostOperation(
        id="files.export",
        title="Write text to the file a write ref names",
        source="HostAuthority.export_file",
        grant="files.export",
        affinity=GUI,
        request=_object(
            {"file": FILE_REF, "content": {"type": "string"}},
            required=("file", "content"),
        ),
        result=_object(
            {"bytes_written": {"type": "integer"}, "name": {"type": "string"}},
            required=("bytes_written", "name"),
        ),
        request_name="ExportRequest",
        result_name="ExportResult",
    ),
    HostOperation(
        id="network.fetch",
        title="Perform one HTTP request through the view's network grant",
        source="NetworkTransport.send",
        grant="network.fetch",
        affinity=GUI,
        request=FETCH_REQUEST,
        events={"data": FETCH_RESPONSE},
        request_name="FetchRequest",
    ),
)

#: Protocol methods deliberately absent from the wire, with the reason. A method
#: missing from both this mapping and :data:`HOST_OPERATIONS` is a test failure.
DEFERRED_HOST_METHODS: Mapping[str, str] = {
    "Layers.selection": (
        "returns every selected feature id; unbounded, and needs the paging the "
        "protocol does not have for it yet"
    ),
    "Project.add_layer": "mutates the open project; arrives with the mutation slice",
    "Settings.set": "mutates persisted state; arrives with the mutation slice",
    "Algorithms.execute": (
        "long-running; needs the job and stream surface (TASK-15, TASK-14), not a "
        "request that times out into an unknown outcome"
    ),
}


def host_grants() -> dict[str, str]:
    """Return the canonical grant each operation needs, keyed by operation id."""
    return {operation.id: operation.grant for operation in HOST_OPERATIONS}


def host_description() -> dict[str, Any]:
    """Return the manifest as the description shape the generator renders."""
    return {
        "schema_version": HOST_SCHEMA_VERSION,
        "id": "qgis.host",
        "title": "QGIS host services",
        "actions": [
            operation.to_description()
            for operation in HOST_OPERATIONS
            if operation.events is None
        ],
        "streams": [
            operation.to_description()
            for operation in HOST_OPERATIONS
            if operation.events is not None
        ],
    }


@dataclass(frozen=True)
class HostServices:
    """The curated Protocols, plus the authority that scopes files and network.

    ``authority`` mints the file refs ``layers.open_vector`` and
    ``files.export`` accept and holds each view's network grant; the
    application mints refs on it after a picker closes and grants network per
    view. ``network`` is the TASK-5 transport ``network.fetch`` sends through;
    without one the operation is declared but fails, never silently served.
    """

    layers: Layers
    project: Project
    settings: Settings
    styles: Styles
    notifications: Notifications
    authority: HostAuthority = field(default_factory=HostAuthority)
    network: NetworkTransport | None = None

    @classmethod
    def from_context(
        cls,
        context: PluginContext,
        *,
        authority: HostAuthority | None = None,
        network: NetworkTransport | None = None,
    ) -> HostServices:
        """Wrap the services a plugin context already holds, instance for instance.

        This is how a page and a Python handler end up reading one project:
        the bridge answers ``layers.list`` from the very ``Layers`` the plugin
        reaches as ``self.ctx.layers``. A context missing one of the four
        required services fails here, by capability name, before anything is
        registered. ``network`` is the transport ``network.fetch`` sends through;
        left out, it is the transport under the context's own client when that
        client exposes one (``NetworkClient.transport``), so a page's fetch and
        a handler's ``await self.ctx.network.get(...)`` leave through one door.
        """
        if network is None and context.network is not None:
            network = getattr(context.network, "transport", None)
        return cls(
            layers=context.require_layers(),
            project=context.require_project(),
            settings=context.require_settings(),
            styles=context.require_styles(),
            notifications=context.notifications,
            authority=authority if authority is not None else HostAuthority(),
            network=network,
        )


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
        "network.fetch": network_fetch,
    }


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
