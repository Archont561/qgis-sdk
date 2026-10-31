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
    BLOB_CHUNK,
    BLOB_REQUEST,
    EDIT_ADD_REQUEST,
    EDIT_ADD_RESULT,
    EDIT_BEGIN_REQUEST,
    EDIT_DELETE_REQUEST,
    EDIT_PENDING_RESULT,
    EDIT_SESSION_REQUEST,
    EDIT_SESSION_RESULT,
    EDIT_UPDATE_REQUEST,
    EXPRESSION_REQUEST,
    FEATURE_PAGE_RESULT,
    FEATURE_QUERY,
    FEATURE_REQUEST,
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
from qgis_sdk.models.features import (
    EDIT_OUTCOME,
    EXPRESSION_CHECK,
    EXPRESSION_OUTCOME,
    FEATURE,
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
        id="blob.get",
        title="Read one bounded chunk of a payload the host kept for this view",
        source="HostAuthority.read_blob",
        grant="blob.read",
        affinity=GUI,
        request=BLOB_REQUEST,
        result=BLOB_CHUNK,
        request_name="BlobRequest",
        result_name="BlobChunk",
    ),
    HostOperation(
        id="features.page",
        title="Stream the features of one layer, one bounded page per event",
        source="Features.page",
        grant="features.read",
        affinity=GUI,
        request=FEATURE_QUERY,
        events={"data": FEATURE_PAGE_RESULT},
        request_name="FeaturePageRequest",
    ),
    HostOperation(
        id="features.get",
        title="Read one feature by id in a chosen geometry encoding",
        source="Features.feature",
        grant="features.read",
        affinity=GUI,
        request=FEATURE_REQUEST,
        result=FEATURE,
        request_name="FeatureRequest",
        result_name="Feature",
    ),
    HostOperation(
        id="expressions.evaluate",
        title="Evaluate one expression, optionally against a layer and a feature",
        source="Features.evaluate",
        grant="expressions.evaluate",
        affinity=GUI,
        request=EXPRESSION_REQUEST,
        result=EXPRESSION_OUTCOME,
        request_name="ExpressionRequest",
        result_name="ExpressionOutcome",
    ),
    HostOperation(
        id="expressions.validate",
        title="Parse one expression and say whether it would run",
        source="Features.check",
        grant="expressions.evaluate",
        affinity=GUI,
        request=EXPRESSION_REQUEST,
        result=EXPRESSION_CHECK,
        request_name="ExpressionRequest",
        result_name="ExpressionCheck",
    ),
    HostOperation(
        id="editing.begin",
        title="Open a view-owned editing session over one layer",
        source="Features.begin_edit",
        grant="features.edit",
        affinity=GUI,
        request=EDIT_BEGIN_REQUEST,
        result=EDIT_SESSION_RESULT,
        request_name="EditBeginRequest",
        result_name="EditSessionInfo",
    ),
    HostOperation(
        id="editing.add",
        title="Buffer one new feature in an editing session",
        source="EditingSession.add",
        grant="features.edit",
        affinity=GUI,
        request=EDIT_ADD_REQUEST,
        result=EDIT_ADD_RESULT,
        request_name="EditAddRequest",
        result_name="EditAddResult",
    ),
    HostOperation(
        id="editing.update",
        title="Buffer a change to one feature in an editing session",
        source="EditingSession.update",
        grant="features.edit",
        affinity=GUI,
        request=EDIT_UPDATE_REQUEST,
        result=EDIT_PENDING_RESULT,
        request_name="EditUpdateRequest",
        result_name="EditPendingResult",
    ),
    HostOperation(
        id="editing.delete",
        title="Buffer the deletion of one feature in an editing session",
        source="EditingSession.delete",
        grant="features.edit",
        affinity=GUI,
        request=EDIT_DELETE_REQUEST,
        result=EDIT_PENDING_RESULT,
        request_name="EditDeleteRequest",
        result_name="EditPendingResult",
    ),
    HostOperation(
        id="editing.commit",
        title="Write an editing session's buffer and report what the provider did",
        source="EditingSession.commit",
        grant="features.edit",
        affinity=GUI,
        request=EDIT_SESSION_REQUEST,
        result=EDIT_OUTCOME,
        request_name="EditSessionRequest",
        result_name="EditOutcome",
    ),
    HostOperation(
        id="editing.rollback",
        title="Discard an editing session's buffer",
        source="EditingSession.rollback",
        grant="features.edit",
        affinity=GUI,
        request=EDIT_SESSION_REQUEST,
        result=EDIT_PENDING_RESULT,
        request_name="EditSessionRequest",
        result_name="EditPendingResult",
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
    "EditingSession.close": (
        "a session ends with the view that began it, so the dispatcher closes it "
        "on dispose and a page never closes a session a later message names"
    ),
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


def host_grant_names() -> tuple[str, ...]:
    """Return the canonical grant names, sorted: the one vocabulary (decision-54).

    Every client that names authority reads this list - the page's
    ``[tool.qgis-sdk.web] grants``, the console's
    ``[tool.qgis-sdk.console] grants``, the manifest, the coverage map and the
    ``GRANT001`` finding - so a name cannot be a grant for one client and a typo
    for another.
    """
    return tuple(sorted({operation.grant for operation in HOST_OPERATIONS}))


def host_operation_ids() -> tuple[str, ...]:
    """Return every declared operation id, in catalogue order."""
    return tuple(operation.id for operation in HOST_OPERATIONS)


def granted_operations(grants: Sequence[str]) -> tuple[str, ...]:
    """Return the operation ids a project's ``grants`` list selects (decision-43).

    Each entry is either a grant (``layers.read`` selects every operation
    that needs it) or one operation id (``project.layer_ids``). The result
    keeps the catalogue's order without duplicates - what ``only=`` of
    :func:`register_host_operations` expects. An entry that is neither is a
    typo that would otherwise narrow the surface in silence, so it raises.
    """
    wanted = set(grants)
    operation_ids = host_operation_ids()
    known = set(operation_ids) | set(host_grant_names())
    for entry in grants:
        if entry not in known:
            raise QgisSdkBridgeError(
                f"unknown host grant {entry!r}; grants are "
                f"{', '.join(host_grant_names())} and "
                f"operation ids are {', '.join(operation_ids)}"
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
