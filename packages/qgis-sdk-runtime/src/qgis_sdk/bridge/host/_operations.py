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
    ANNOTATION_LAYER_INFO,
    ATLAS_EXPORT_RESULT,
    ATLAS_LAYOUT_REQUEST,
    BATCH_REQUEST,
    BATCH_RESULT,
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
    EXPORT_LAYOUT_REQUEST,
    EXPRESSION_REQUEST,
    FEATURE_PAGE_RESULT,
    FEATURE_QUERY,
    FEATURE_REQUEST,
    FETCH_REQUEST,
    FETCH_RESPONSE,
    GUI,
    LAYER_INFO,
    LAYOUT_EXPORT_RESULT,
    LOAD_LAYOUT_TEMPLATE_REQUEST,
    MESH_LAYER_INFO,
    PAGE_REQUEST,
    POINT_CLOUD_LAYER_INFO,
    PROVIDER_INFO,
    RASTER_LAYER_INFO,
    RUN_MODEL_REQUEST,
    RUN_REQUEST,
    RUN_RESULT,
    TILED_SCENE_LAYER_INFO,
    VECTOR_LAYER_INFO,
    VECTOR_TILE_LAYER_INFO,
    _array,
    _object,
    page_result,
)
from qgis_sdk.bridge.protocol import HOST_SCHEMA_VERSION
from qgis_sdk.models.canvas import (
    CANVAS_EXTENT,
    CANVAS_POINT,
    CAPTURE_REQUEST,
    MAP_THEMES,
    ZOOM_REQUEST,
)
from qgis_sdk.models.connections import (
    AUTH_CONFIGURATION,
    CONNECTION_INFO,
    CONNECTION_ITEM,
    CONNECTION_TEST,
)
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.models.features import (
    EDIT_OUTCOME,
    EXPRESSION_CHECK,
    EXPRESSION_OUTCOME,
    FEATURE,
    GEOMETRY,
)
from qgis_sdk.models.layers import RASTER_SAMPLE, RASTER_STATISTICS
from qgis_sdk.models.layouts import LAYOUT_INFO
from qgis_sdk.models.project import (
    BOOKMARK,
    LAYER_TREE,
    PROJECT_CHANGE,
    PROJECT_ENTRY,
    PROJECT_FILE,
)
from qgis_sdk.models.symbology import (
    LABELLING,
    RENDERER,
    STYLE_ENTRY,
    STYLE_FORMATS,
    STYLE_MANAGER_KINDS,
    STYLE_TEXT,
)

#: Project variables and custom properties: one small, project-owned list,
#: answered whole rather than paged, because a project file bounds it.
_PROJECT_ENTRIES = _array(PROJECT_ENTRY)

#: The project's bookmarks, bounded the same way.
_BOOKMARKS = _array(BOOKMARK)

#: The project's print layouts, paged like every other list: a project file
#: bounds how many it can hold, but "bounded" is not "small enough to inline".
_LAYOUTS = page_result(LAYOUT_INFO)

#: The style manager's entries, paged for the same reason: a style database is a
#: user's library, and a page cannot carry an unbounded one.
_STYLE_ENTRIES = page_result(STYLE_ENTRY)


@dataclass(frozen=True, slots=True)
class HostOperation:
    """One operation of the host surface, declared rather than inferred.

    ``source`` names the Protocol method it wraps so a test can prove the two
    lists stay in step, and ``grant`` is the canonical permission an application
    checks - a namespace-wide flag would grant every future method at once.

    ``destructive`` is the annotation the agent surface reads (decision-27
    point 2, decision-49 point 4): an operation that replaces or discards
    project state - a write, a save, a read over the open project, a removal -
    says so here, so the consent list can ask each time and the audit log can
    mark the call. A read never carries it, and nothing infers it from the
    operation's name.

    ``credential`` is its own annotation, never folded into ``destructive``
    (TASK-92): an operation that authenticates with stored material or reads or
    re-binds the authentication registry says so here. The two axes answer
    different questions - "will this change my project?" and "will this touch
    my credentials?" - and the consent list shows them distinctly, so a read
    that spends a password is not hidden among the writes and a write that
    never authenticates is not dressed up as a credential act.
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
    destructive: bool = False
    credential: bool = False

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
        described["destructive"] = self.destructive
        described["credential"] = self.credential
        return described


HOST_OPERATIONS: tuple[HostOperation, ...] = (
    HostOperation(
        id="layers.list",
        title="List the layers this runtime opened",
        source="Layers.list_layers",
        grant="layers.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result(LAYER_INFO),
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
        result=LAYER_INFO,
        request_name="LayerRequest",
        result_name="LayerInfo",
    ),
    HostOperation(
        id="project.layer_ids",
        title="List the project's layer ids in project order",
        source="Project.layer_ids",
        grant="project.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result({"type": "string"}),
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
        # Applying a style replaces the layer's whole symbology: an agent that
        # could do it silently would change how a map is drawn without consent.
        destructive=True,
    ),
    HostOperation(
        id="symbology.get",
        title="Describe the renderer drawing a layer",
        source="Styles.symbology",
        grant="symbology.read",
        affinity=GUI,
        request=_object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=RENDERER,
        request_name="SymbologyRequest",
        result_name="Renderer",
    ),
    HostOperation(
        id="symbology.set",
        title="Draw a layer with a described renderer",
        source="Styles.set_symbology",
        grant="symbology.write",
        affinity=GUI,
        request=_object(
            {"layer_id": {"type": "string"}, "renderer": RENDERER},
            required=("layer_id", "renderer"),
        ),
        result=_NOTHING,
        request_name="SetSymbologyRequest",
        destructive=True,
    ),
    HostOperation(
        id="labelling.get",
        title="Describe how a layer's features are labelled",
        source="Styles.labelling",
        grant="symbology.read",
        affinity=GUI,
        request=_object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=LABELLING,
        request_name="LabellingRequest",
        result_name="Labelling",
    ),
    HostOperation(
        id="labelling.set",
        title="Label a layer's features, or switch labelling off",
        source="Styles.set_labelling",
        grant="symbology.write",
        affinity=GUI,
        request=_object(
            {"layer_id": {"type": "string"}, "labelling": LABELLING},
            required=("layer_id", "labelling"),
        ),
        result=_NOTHING,
        request_name="SetLabellingRequest",
        destructive=True,
    ),
    HostOperation(
        id="styles.list",
        title="List what the QGIS style manager offers",
        source="Styles.list_styles",
        grant="styles.read",
        affinity=GUI,
        request=_object({"kind": {"enum": list(STYLE_MANAGER_KINDS)}}),
        result=_STYLE_ENTRIES,
        request_name="StyleListRequest",
        result_name="StyleEntries",
    ),
    HostOperation(
        id="styles.export",
        title="Export a layer's style as QML or SLD text",
        source="Styles.export_style",
        grant="styles.read",
        affinity=GUI,
        request=_object(
            {
                "layer_id": {"type": "string"},
                "format": {"enum": list(STYLE_FORMATS)},
            },
            required=("layer_id", "format"),
        ),
        result=STYLE_TEXT,
        request_name="ExportStyleRequest",
        result_name="StyleText",
    ),
    HostOperation(
        id="styles.import",
        title="Apply QML or SLD text to a layer",
        source="Styles.import_style",
        grant="styles.write",
        affinity=GUI,
        request=_object(
            {
                "layer_id": {"type": "string"},
                "format": {"enum": list(STYLE_FORMATS)},
                "text": {"type": "string"},
            },
            required=("layer_id", "format", "text"),
        ),
        result=_NOTHING,
        request_name="ImportStyleRequest",
        destructive=True,
    ),
    HostOperation(
        id="connections.list",
        title="List the registered data-source connections",
        source="Connections.list_connections",
        grant="connections.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result(CONNECTION_INFO),
        request_name="PageRequest",
        result_name="ConnectionPage",
    ),
    HostOperation(
        id="connections.describe",
        title="Describe one registered connection",
        source="Connections.connection",
        grant="connections.read",
        affinity=GUI,
        request=_object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
            },
            required=("provider", "connection"),
        ),
        result=CONNECTION_INFO,
        request_name="ConnectionRequest",
        result_name="ConnectionInfo",
    ),
    HostOperation(
        id="connections.browse",
        title="Browse the schemas or the tables one connection holds",
        source="Connections.browse",
        grant="connections.read",
        affinity=GUI,
        request=_object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
                "schema": {"type": "string"},
            },
            required=("provider", "connection"),
        ),
        result=page_result(CONNECTION_ITEM),
        request_name="ConnectionBrowseRequest",
        result_name="ConnectionItemPage",
        # A browse queries the database with the authentication the connection
        # stores; a page cannot walk a server's catalog without spending it.
        credential=True,
    ),
    HostOperation(
        id="connections.open_layer",
        title="Open one table of a connection as a vector layer",
        source="Connections.open_layer",
        grant="layers.open",
        affinity=GUI,
        request=_object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
                "schema": {"type": "string"},
                "item": {"type": "string"},
            },
            required=("provider", "connection", "schema", "item"),
        ),
        result=VECTOR_LAYER_INFO,
        request_name="ConnectionItemRequest",
        result_name="VectorLayerInfo",
        # Opening the table authenticates exactly as browsing it does.
        credential=True,
    ),
    HostOperation(
        id="connections.test",
        title="Test whether one registered connection answers",
        source="Connections.test",
        grant="connections.read",
        affinity=GUI,
        request=_object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
            },
            required=("provider", "connection"),
        ),
        result=CONNECTION_TEST,
        request_name="ConnectionRequest",
        result_name="ConnectionTest",
        # Testing spends the stored authentication against the server: the one
        # call whose whole purpose is to try the credential.
        credential=True,
    ),
    HostOperation(
        id="auth.configurations",
        title="List the authentication configurations by id and name",
        source="Connections.auth_configurations",
        grant="auth.read",
        affinity=GUI,
        request=PAGE_REQUEST,
        result=page_result(AUTH_CONFIGURATION),
        request_name="PageRequest",
        result_name="AuthConfigurationPage",
        # Reading the credential registry is a credential act even though the
        # answer carries ids and names only.
        credential=True,
    ),
    HostOperation(
        id="auth.attach",
        title="Attach one authentication configuration to one connection",
        source="Connections.attach_auth_config",
        grant="auth.write",
        affinity=GUI,
        request=_object(
            {
                "provider": {"type": "string"},
                "connection": {"type": "string"},
                "auth_config": {"type": "string"},
            },
            required=("provider", "connection", "auth_config"),
        ),
        result=_NOTHING,
        request_name="AuthAttachRequest",
        # It replaces how the connection authenticates - the old password or
        # configuration stops being spent - and it re-binds a credential, so it
        # carries both annotations and the consent list asks twice over.
        destructive=True,
        credential=True,
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
        id="layers.open_mesh",
        title="Open the mesh dataset a file ref names",
        source="Layers.open_mesh",
        grant="layers.open",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=MESH_LAYER_INFO,
        request_name="OpenMeshRequest",
        result_name="MeshLayerInfo",
    ),
    HostOperation(
        id="layers.open_point_cloud",
        title="Open the point cloud dataset a file ref names",
        source="Layers.open_point_cloud",
        grant="layers.open",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=POINT_CLOUD_LAYER_INFO,
        request_name="OpenPointCloudRequest",
        result_name="PointCloudLayerInfo",
    ),
    HostOperation(
        id="layers.open_vector_tile",
        title="Open the vector tile source a file ref names",
        source="Layers.open_vector_tile",
        grant="layers.open",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=VECTOR_TILE_LAYER_INFO,
        request_name="OpenVectorTileRequest",
        result_name="VectorTileLayerInfo",
    ),
    HostOperation(
        id="layers.open_annotation",
        title="Open an annotation layer by the name it is created under",
        source="Layers.open_annotation",
        grant="layers.open",
        affinity=GUI,
        # A name a layer is created under cannot be blank: the wire refuses it
        # here, so a handler never creates a layer no page can name again.
        request=_object(
            {"name": {"type": "string", "pattern": r".*\S.*"}},
            required=("name",),
        ),
        result=ANNOTATION_LAYER_INFO,
        request_name="OpenAnnotationRequest",
        result_name="AnnotationLayerInfo",
    ),
    HostOperation(
        id="layers.open_tiled_scene",
        title="Open the tiled scene dataset a file ref names",
        source="Layers.open_tiled_scene",
        grant="layers.open",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=TILED_SCENE_LAYER_INFO,
        request_name="OpenTiledSceneRequest",
        result_name="TiledSceneLayerInfo",
    ),
    HostOperation(
        id="rasters.open",
        title="Open the raster dataset a file ref names",
        source="Rasters.open_raster",
        grant="rasters.open",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=RASTER_LAYER_INFO,
        request_name="OpenRasterRequest",
        result_name="RasterLayerInfo",
    ),
    HostOperation(
        id="rasters.get",
        title="Describe one opened raster by its bands",
        source="Rasters.raster",
        grant="rasters.read",
        affinity=GUI,
        request=_object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=RASTER_LAYER_INFO,
        request_name="RasterRequest",
        result_name="RasterLayerInfo",
    ),
    HostOperation(
        id="rasters.statistics",
        title="Measure one band of an opened raster",
        source="Rasters.statistics",
        grant="rasters.read",
        affinity=GUI,
        request=_object(
            {"layer_id": {"type": "string"}, "band": {"type": "integer", "minimum": 1}},
            required=("layer_id", "band"),
        ),
        result=RASTER_STATISTICS,
        request_name="BandRequest",
        result_name="RasterStatistics",
    ),
    HostOperation(
        id="rasters.sample",
        title="Read the value of every band at one point",
        source="Rasters.sample",
        grant="rasters.read",
        affinity=GUI,
        request=_object(
            {
                "layer_id": {"type": "string"},
                "point": CANVAS_POINT,
                "band": {"type": "integer", "minimum": 1},
            },
            required=("layer_id", "point"),
        ),
        result=RASTER_SAMPLE,
        request_name="SampleRequest",
        result_name="RasterSample",
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
        result=page_result(PROVIDER_INFO),
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
        result=page_result(ALGORITHM_SUMMARY),
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
        id="algorithms.run_model",
        title="Run one model file and return its outputs",
        source="Algorithms.run_model",
        grant="algorithms.run",
        affinity=GUI,
        request=RUN_MODEL_REQUEST,
        result=RUN_RESULT,
        request_name="RunModelRequest",
        result_name="RunResult",
    ),
    HostOperation(
        id="algorithms.batch",
        title="Run several requests in order and return every result",
        source="Algorithms.batch",
        grant="algorithms.run",
        affinity=GUI,
        request=BATCH_REQUEST,
        result=BATCH_RESULT,
        request_name="BatchRequest",
        result_name="BatchResult",
        # The service's batch is the job form, with per-item progress and a
        # cancel button; a page has no job-status operation to follow one
        # with, so `algorithms.batch` runs the same requests in the request
        # that asked for them (the `layouts.export` precedent).
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
        id="canvas.extent",
        title="Read the map canvas's extent",
        source="Canvas.extent",
        grant="canvas.read",
        affinity=GUI,
        request=_object({}),
        result=CANVAS_EXTENT,
        result_name="CanvasExtent",
    ),
    HostOperation(
        id="canvas.scale",
        title="Read the map canvas's scale denominator",
        source="Canvas.scale",
        grant="canvas.read",
        affinity=GUI,
        request=_object({}),
        result={"type": "number"},
    ),
    HostOperation(
        id="canvas.crs",
        title="Read the map canvas's CRS",
        source="Canvas.crs",
        grant="canvas.read",
        affinity=GUI,
        request=_object({}),
        result={"anyOf": [{"type": "string"}, {"type": "null"}]},
    ),
    HostOperation(
        id="canvas.center",
        title="Read the map canvas's centre",
        source="Canvas.center",
        grant="canvas.read",
        affinity=GUI,
        request=_object({}),
        result=CANVAS_POINT,
        result_name="CanvasPoint",
    ),
    HostOperation(
        id="canvas.zoom_to",
        title="Move the map onto a layer, its selection or an extent",
        source="Canvas.zoom_to",
        grant="canvas.control",
        affinity=GUI,
        request=ZOOM_REQUEST,
        result=CANVAS_EXTENT,
        request_name="ZoomRequest",
        result_name="CanvasExtent",
    ),
    HostOperation(
        id="canvas.refresh",
        title="Redraw the map without moving it",
        source="Canvas.refresh",
        grant="canvas.control",
        affinity=GUI,
        request=_object({}),
        result=_NOTHING,
    ),
    HostOperation(
        id="canvas.themes",
        title="List the project's map themes and the active one",
        source="Canvas.themes",
        grant="canvas.read",
        affinity=GUI,
        request=_object({}),
        result=MAP_THEMES,
        result_name="MapThemes",
    ),
    HostOperation(
        id="canvas.apply_theme",
        title="Draw the map with one map theme",
        source="Canvas.apply_theme",
        grant="canvas.control",
        affinity=GUI,
        request=_object({"name": {"type": "string"}}, required=("name",)),
        result=MAP_THEMES,
        request_name="ThemeRequest",
        result_name="MapThemes",
    ),
    HostOperation(
        id="canvas.extent_changed",
        title="Follow the map canvas as the user moves it",
        source="Canvas.watch_extent",
        grant="canvas.read",
        affinity=GUI,
        request=_object({}),
        events={"data": CANVAS_EXTENT},
    ),
    HostOperation(
        id="canvas.capture",
        title="Draw one geometry with a capture tool and return it",
        source="Canvas.capture",
        grant="canvas.control",
        affinity=GUI,
        request=CAPTURE_REQUEST,
        events={"data": GEOMETRY},
        request_name="CaptureRequest",
    ),
    HostOperation(
        id="project.tree",
        title="Read the project's layer tree",
        source="Project.layer_tree",
        grant="project.read",
        affinity=GUI,
        request=_object({}),
        result=LAYER_TREE,
        result_name="LayerTree",
    ),
    HostOperation(
        id="project.add_layer",
        title="Add an owned layer to the project, into a group if named",
        source="Project.add_layer",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {"layer_id": {"type": "string"}, "group": {"type": "string"}},
            required=("layer_id",),
        ),
        result_name="LayerTree",
        result=LAYER_TREE,
    ),
    HostOperation(
        id="project.remove_layer",
        title="Remove one layer from the project",
        source="Project.remove_layer",
        grant="project.write",
        affinity=GUI,
        request=_object({"layer_id": {"type": "string"}}, required=("layer_id",)),
        result=LAYER_TREE,
        result_name="LayerTree",
        destructive=True,
    ),
    HostOperation(
        id="project.move_layer",
        title="Move one layer within the project tree",
        source="Project.move_layer",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {
                "layer_id": {"type": "string"},
                "group": {"type": "string"},
                "index": {"type": "integer", "minimum": 0},
            },
            required=("layer_id",),
        ),
        result=LAYER_TREE,
        result_name="LayerTree",
    ),
    HostOperation(
        id="project.set_visible",
        title="Show or hide one node of the project tree",
        source="Project.set_visible",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {"node_id": {"type": "string"}, "visible": {"type": "boolean"}},
            required=("node_id", "visible"),
        ),
        result=LAYER_TREE,
        result_name="LayerTree",
    ),
    HostOperation(
        id="project.crs",
        title="Read the project's CRS",
        source="Project.crs",
        grant="project.read",
        affinity=GUI,
        request=_object({}),
        result={"anyOf": [{"type": "string"}, {"type": "null"}]},
    ),
    HostOperation(
        id="project.set_crs",
        title="Set the project's CRS",
        source="Project.set_crs",
        grant="project.write",
        affinity=GUI,
        request=_object({"auth_id": {"type": "string"}}, required=("auth_id",)),
        result={"type": "string"},
    ),
    HostOperation(
        id="project.variables",
        title="Read the project's expression variables",
        source="Project.variables",
        grant="project.read",
        affinity=GUI,
        request=_object({}),
        result=_PROJECT_ENTRIES,
        result_name="ProjectEntries",
    ),
    HostOperation(
        id="project.set_variable",
        title="Set one project expression variable",
        source="Project.set_variable",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {"name": {"type": "string"}, "value": {"type": "string"}},
            required=("name", "value"),
        ),
        result=_PROJECT_ENTRIES,
        result_name="ProjectEntries",
    ),
    HostOperation(
        id="project.unset_variable",
        title="Remove one project expression variable",
        source="Project.unset_variable",
        grant="project.write",
        affinity=GUI,
        request=_object({"name": {"type": "string"}}, required=("name",)),
        result=_PROJECT_ENTRIES,
        result_name="ProjectEntries",
        destructive=True,
    ),
    HostOperation(
        id="project.properties",
        title="Read the project's custom properties",
        source="Project.custom_properties",
        grant="project.read",
        affinity=GUI,
        request=_object({}),
        result=_PROJECT_ENTRIES,
        result_name="ProjectEntries",
    ),
    HostOperation(
        id="project.set_property",
        title="Set one project custom property",
        source="Project.set_custom_property",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {"name": {"type": "string"}, "value": {"type": "string"}},
            required=("name", "value"),
        ),
        result=_PROJECT_ENTRIES,
        result_name="ProjectEntries",
    ),
    HostOperation(
        id="project.unset_property",
        title="Remove one project custom property",
        source="Project.unset_custom_property",
        grant="project.write",
        affinity=GUI,
        request=_object({"name": {"type": "string"}}, required=("name",)),
        result=_PROJECT_ENTRIES,
        result_name="ProjectEntries",
        destructive=True,
    ),
    HostOperation(
        id="project.bookmarks",
        title="Read the project's bookmarks",
        source="Project.bookmarks",
        grant="project.read",
        affinity=GUI,
        request=_object({}),
        result=_BOOKMARKS,
        result_name="Bookmarks",
    ),
    HostOperation(
        id="project.bookmark",
        title="Read one bookmark by name",
        source="Project.bookmark",
        grant="project.read",
        affinity=GUI,
        request=_object({"name": {"type": "string"}}, required=("name",)),
        result=BOOKMARK,
        result_name="Bookmark",
    ),
    HostOperation(
        id="project.add_bookmark",
        title="Bookmark an extent",
        source="Project.add_bookmark",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {"name": {"type": "string"}, "extent": CANVAS_EXTENT},
            required=("name", "extent"),
        ),
        result=_BOOKMARKS,
        result_name="Bookmarks",
    ),
    HostOperation(
        id="project.remove_bookmark",
        title="Remove one bookmark by name",
        source="Project.remove_bookmark",
        grant="project.write",
        affinity=GUI,
        request=_object({"name": {"type": "string"}}, required=("name",)),
        result=_BOOKMARKS,
        result_name="Bookmarks",
        destructive=True,
    ),
    HostOperation(
        id="project.read",
        title="Open the project file a read ref names",
        source="Project.read",
        grant="project.write",
        affinity=GUI,
        request=_object({"file": FILE_REF}, required=("file",)),
        result=LAYER_TREE,
        request_name="ReadProjectRequest",
        result_name="LayerTree",
        destructive=True,
    ),
    HostOperation(
        id="project.write",
        title="Write the project to the file a write ref names",
        source="Project.write",
        grant="project.write",
        affinity=GUI,
        request=_object(
            {"file": FILE_REF, "overwrite": {"type": "boolean"}}, required=("file",)
        ),
        result=PROJECT_FILE,
        request_name="WriteProjectRequest",
        result_name="ProjectFile",
        destructive=True,
    ),
    HostOperation(
        id="project.save",
        title="Save the project to the file it was opened from",
        source="Project.save",
        grant="project.write",
        affinity=GUI,
        request=_object({}),
        result=PROJECT_FILE,
        result_name="ProjectFile",
        destructive=True,
    ),
    HostOperation(
        id="project.changed",
        title="Follow the project as it changes",
        source="Project.watch_changes",
        grant="project.read",
        affinity=GUI,
        request=_object({}),
        events={"data": PROJECT_CHANGE},
    ),
    HostOperation(
        id="layouts.list",
        title="List the project's print layouts",
        source="Layouts.list",
        grant="layouts.read",
        affinity=GUI,
        request=_object({}),
        result=_LAYOUTS,
        result_name="Layouts",
    ),
    HostOperation(
        id="layouts.load_template",
        title="Load a print-layout template into the project",
        source="Layouts.load_template",
        grant="layouts.write",
        affinity=GUI,
        request=LOAD_LAYOUT_TEMPLATE_REQUEST,
        result=LAYOUT_INFO,
        result_name="LayoutInfo",
    ),
    HostOperation(
        id="layouts.export",
        title="Export one layout to a PDF, PNG or SVG file",
        source="Layouts.render",
        grant="layouts.export",
        affinity=GUI,
        request=EXPORT_LAYOUT_REQUEST,
        result=LAYOUT_EXPORT_RESULT,
        request_name="ExportLayoutRequest",
        result_name="LayoutExport",
        # Overwrite is the reason: the export replaces a file the page's own
        # write ref already names, and the annotation is what the agent consent
        # list reads to ask first (decision-49 point 4).
        destructive=True,
    ),
    HostOperation(
        id="layouts.atlas",
        title="Run one layout's atlas, one file per coverage feature",
        source="Layouts.render_atlas",
        grant="layouts.export",
        affinity=GUI,
        request=ATLAS_LAYOUT_REQUEST,
        result=ATLAS_EXPORT_RESULT,
        request_name="AtlasLayoutRequest",
        result_name="AtlasExport",
        destructive=True,
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
        # The request may name an ``auth_config``: the fetch then spends an
        # authentication configuration the caller never sees the secret of.
        credential=True,
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
    "Rasters.export_raster": (
        "writes a whole raster, which is minutes of work on a real dataset; a "
        "page asks its plugin action, which runs it as a @job on a worker and "
        "hands the file back as a ref (the layouts precedent, decision-54 point 3)"
    ),
    "Layers.export_vector": (
        "takes a filesystem destination, which a page never supplies (decision-20); "
        "a page exports through `files.export` and a host-minted write ref, and a "
        "plugin action resolves a bare file name against a host-chosen directory "
        "(the reference plugin's `export_layer`)"
    ),
    "Layouts.export": (
        "submits the render as a job and answers its handle; a page has no "
        "job-status operation to follow one with, so `layouts.export` runs the "
        "same render in the request that asked for it and answers the file"
    ),
    "Layouts.run_atlas": (
        "the job form of `layouts.atlas`: one task in the plugin's task bar. A "
        "page's run is the request itself, which ends with one ref per page"
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
