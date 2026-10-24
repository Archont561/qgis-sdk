"""The curated host surface a web view may call, and the wiring that answers it.

Decision-27 draws the line this module implements: a page may reach the five
curated Protocols in :mod:`qgis_sdk.services` - and nothing else of the QGIS API.
What a page gets is not "the host": it is a declared list of operations, each
with a request and a result schema, a canonical grant, a thread affinity and the
Protocol method it wraps. The same list is what the TypeScript module in
``@archont561/qgis-sdk-bridge/host`` is generated from, so the surface a page
sees cannot drift from the surface the host answers.

Two rules are enforced by the declaration rather than by review:

* **Deferred is a recorded decision.** Every method of a curated Protocol is
  either one of :data:`HOST_OPERATIONS` or one of
  :data:`DEFERRED_HOST_METHODS` with the reason it is absent. A test reflects
  the Protocols and fails when a method appears in neither, so adding a Protocol
  method cannot quietly become an unreachable - or, worse, an unintentionally
  reachable - part of the wire surface.
* **No page-supplied paths, no unbounded arrays.** Nothing here takes a
  filesystem path (``Layers.open_vector`` waits for TASK-20's host-minted
  ``FileRef``), and every list that can grow is paged by
  :func:`_page` before it crosses ``QWebChannel``.

This slice is read-only apart from ``styles.apply``, which the decision keeps in
the first slice because it is the one mutation a style panel needs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Any

from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.services.contracts import Notifications
from qgis_sdk.services.layers import Layers
from qgis_sdk.services.project import Project
from qgis_sdk.services.settings import Settings
from qgis_sdk.services.styles import Styles

from .protocol import HOST_SCHEMA_VERSION, BridgeOperation

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from .dispatch import Dispatcher

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
    result: Mapping[str, Any]
    request_name: str | None = None
    result_name: str | None = None

    def to_description(self) -> dict[str, Any]:
        """Return the action-shaped record the generator already understands."""
        described: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "handler": self.id,
            "request": self.request,
            "result": self.result,
        }
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
)

#: Protocol methods deliberately absent from the wire, with the reason. A method
#: missing from both this mapping and :data:`HOST_OPERATIONS` is a test failure.
DEFERRED_HOST_METHODS: Mapping[str, str] = {
    "Layers.open_vector": (
        "takes a filesystem path; a page-supplied path is arbitrary local file "
        "read, so it waits for a host-minted FileRef (TASK-20)"
    ),
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
        "actions": [operation.to_description() for operation in HOST_OPERATIONS],
    }


@dataclass(frozen=True)
class HostServices:
    """The five curated Protocols, as the application already implements them."""

    layers: Layers
    project: Project
    settings: Settings
    styles: Styles
    notifications: Notifications


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


def _handlers(services: HostServices) -> dict[str, Callable[[Mapping[str, Any]], Any]]:
    """Bind each operation id to the Protocol call and the shape it returns."""

    def layers_list(payload: Mapping[str, Any]) -> dict:
        return _page_of(services.layers.list_layers(), payload)

    def layers_get(payload: Mapping[str, Any]) -> Any:
        return _plain(services.layers.layer(payload["layer_id"]))

    def project_layer_ids(payload: Mapping[str, Any]) -> dict:
        return _page_of(services.project.layer_ids(), payload)

    def settings_get(payload: Mapping[str, Any]) -> Any:
        return services.settings.get(payload["key"], payload.get("default"))

    def notifications_info(payload: Mapping[str, Any]) -> None:
        services.notifications.info(payload["message"])

    def styles_apply(payload: Mapping[str, Any]) -> None:
        services.styles.apply_style(payload["layer_id"], payload["style"])

    return {
        "layers.list": layers_list,
        "layers.get": layers_get,
        "project.layer_ids": project_layer_ids,
        "settings.get": settings_get,
        "notifications.info": notifications_info,
        "styles.apply": styles_apply,
    }


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
        )
        for operation in wanted
    ]
    taken = {operation.id for operation in dispatcher.operations()}
    conflicts = [operation.id for operation in operations if operation.id in taken]
    if conflicts:
        raise QgisSdkBridgeError(
            f"duplicate operation id {conflicts[0]!r}; nothing was registered"
        )
    for operation in operations:
        dispatcher.register(operation, handlers[operation.id])
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
