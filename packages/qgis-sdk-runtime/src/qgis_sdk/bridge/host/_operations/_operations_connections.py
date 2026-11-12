"""The declared operation table, the grants that select from it and the description."""

from __future__ import annotations

from qgis_sdk.bridge.authority import FILE_REF
from qgis_sdk.bridge.host._schemas import (
    _NOTHING,
    ALGORITHM_INFO,
    ALGORITHM_SUMMARY,
    ANNOTATION_LAYER_INFO,
    GUI,
    MESH_LAYER_INFO,
    PAGE_REQUEST,
    POINT_CLOUD_LAYER_INFO,
    PROVIDER_INFO,
    RASTER_LAYER_INFO,
    TILED_SCENE_LAYER_INFO,
    VECTOR_LAYER_INFO,
    VECTOR_TILE_LAYER_INFO,
    object,
    page_result,
)
from qgis_sdk.models.canvas import (
    CANVAS_POINT,
)
from qgis_sdk.models.connections import (
    AUTH_CONFIGURATION,
    CONNECTION_TEST,
)
from qgis_sdk.models.layers import RASTER_SAMPLE, RASTER_STATISTICS

from ._operation import (
    HostOperation,
)

HOST_OPERATIONS_B = (
    HostOperation(
        id="connections.test",
        title="Test whether one registered connection answers",
        source="Connections.test",
        grant="connections.read",
        affinity=GUI,
        request=object(
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
        request=object(
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
        request=object({"file": FILE_REF}, required=("file",)),
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
        request=object({"file": FILE_REF}, required=("file",)),
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
        request=object({"file": FILE_REF}, required=("file",)),
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
        request=object({"file": FILE_REF}, required=("file",)),
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
        request=object(
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
        request=object({"file": FILE_REF}, required=("file",)),
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
        request=object({"file": FILE_REF}, required=("file",)),
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
        request=object({"layer_id": {"type": "string"}}, required=("layer_id",)),
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
        request=object(
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
        request=object(
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
        request=object(
            {"file": FILE_REF, "content": {"type": "string"}},
            required=("file", "content"),
        ),
        result=object(
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
        request=object(
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
        request=object(
            {"algorithm_id": {"type": "string"}}, required=("algorithm_id",)
        ),
        result=ALGORITHM_INFO,
        request_name="AlgorithmRequest",
        result_name="AlgorithmInfo",
    ),
)
