"""The declared operation table, the grants that select from it and the description."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qgis_sdk.bridge.authority import FILE_REF
from qgis_sdk.bridge.host._schemas import (
    _NOTHING,
    ALGORITHM_INFO,
    ALGORITHM_SUMMARY,
    FETCH_REQUEST,
    FETCH_RESPONSE,
    GUI,
    PAGE_REQUEST,
    PROVIDER_INFO,
    RUN_REQUEST,
    RUN_RESULT,
    VECTOR_LAYER_INFO,
    _object,
    _page_result,
)
from qgis_sdk.bridge.protocol import HOST_SCHEMA_VERSION
from qgis_sdk.models.errors import QgisSdkBridgeError


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
        id="algorithms.providers",
        title="List the Processing providers this host registered",
        source="Algorithms.providers",
        grant="algorithms.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=_page_result(PROVIDER_INFO),
        request_name="PageRequest",
        result_name="ProviderPage",
    ),
    HostOperation(
        id="algorithms.list",
        title="List the algorithms of one provider, or of all",
        source="Algorithms.list",
        grant="algorithms.read",
        affinity=GUI,
        request=_object(
            {**PAGE_REQUEST["properties"], "provider": {"type": "string"}},
        ),
        result=_page_result(ALGORITHM_SUMMARY),
        request_name="AlgorithmListRequest",
        result_name="AlgorithmPage",
    ),
    HostOperation(
        id="algorithms.describe",
        title="Describe one algorithm: parameters and outputs",
        source="Algorithms.describe",
        grant="algorithms.read",
        affinity=GUI,
        request=_object(
            {"algorithm_id": {"type": "string"}}, required=("algorithm_id",)
        ),
        result=ALGORITHM_INFO,
        request_name="AlgorithmRequest",
        result_name="AlgorithmInfo",
    ),
    HostOperation(
        id="algorithms.run",
        title="Run one algorithm and return its outputs",
        source="Algorithms.run",
        grant="algorithms.run",
        affinity=GUI,
        request=RUN_REQUEST,
        result=RUN_RESULT,
        request_name="RunAlgorithmRequest",
        result_name="RunResult",
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
_NOTIFICATION_LEVELS_DEFERRED = (
    "a level on the message bar; `notifications.info` stays the one wire operation "
    "until a later protocol version adds levelled feedback without moving "
    "HOST_FINGERPRINT in the middle of a release train"
)

DEFERRED_HOST_METHODS: Mapping[str, str] = {
    "Layers.selection": (
        "returns every selected feature id; unbounded, and needs the paging the "
        "protocol does not have for it yet"
    ),
    "Project.add_layer": "mutates the open project; arrives with the mutation slice",
    "Layers.export_vector": (
        "takes a filesystem destination, which a page never supplies (decision-20); "
        "a page exports through `files.export` and a host-minted write ref, and a "
        "plugin action resolves a bare file name against a host-chosen directory "
        "(the reference plugin's `export_layer`)"
    ),
    "Settings.set": "mutates persisted state; arrives with the mutation slice",
    "Notifications.success": _NOTIFICATION_LEVELS_DEFERRED,
    "Notifications.warning": _NOTIFICATION_LEVELS_DEFERRED,
    "Notifications.critical": _NOTIFICATION_LEVELS_DEFERRED,
    "Notifications.with_action": (
        "attaches a button that runs a plugin action; a page draws its own "
        "buttons over `actions.call` (decision-55), and a host-side button a page "
        "can press needs a later protocol version to carry it"
    ),
    "Algorithms.execute": (
        "the plugin-local provider surface; a page runs any algorithm, the "
        "plugin's own included, through `algorithms.run` (decision-64)"
    ),
}


def host_grants() -> dict[str, str]:
    """Return the canonical grant each operation needs, keyed by operation id."""
    return {operation.id: operation.grant for operation in HOST_OPERATIONS}


def granted_operations(grants: Sequence[str]) -> tuple[str, ...]:
    """Return the operation ids a project's ``grants`` list selects (decision-43).

    Each entry is either a grant (``layers.read`` selects every operation
    that needs it) or one operation id (``project.layer_ids``). The result
    keeps the catalogue's order without duplicates - what ``only=`` of
    :func:`register_host_operations` expects. An entry that is neither is a
    typo that would otherwise narrow the surface in silence, so it raises.
    """
    wanted = set(grants)
    known = {operation.id for operation in HOST_OPERATIONS} | {
        operation.grant for operation in HOST_OPERATIONS
    }
    for entry in grants:
        if entry not in known:
            raise QgisSdkBridgeError(
                f"unknown host grant {entry!r}; grants are "
                f"{', '.join(sorted({o.grant for o in HOST_OPERATIONS}))} and "
                f"operation ids are {', '.join(o.id for o in HOST_OPERATIONS)}"
            )
    return tuple(
        operation.id
        for operation in HOST_OPERATIONS
        if operation.id in wanted or operation.grant in wanted
    )


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
