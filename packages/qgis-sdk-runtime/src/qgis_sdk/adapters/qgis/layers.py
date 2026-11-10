"""PyQGIS-backed layer service.

Native module: importing it needs a QGIS installation, so nothing on the pure
side may import it (``tests/test_pure_imports.py`` guards that). The adapter
returns :class:`~qgis_sdk.models.layers.LayerInfo` values - a
:class:`~qgis_sdk.models.layers.VectorLayerInfo`, one of the five other kinds
this module opens itself, or, when a sibling ``NativeRasters`` opened it, a
:class:`~qgis_sdk.models.layers.RasterLayerInfo` - and never a PyQGIS handle.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from qgis.core import (
    Qgis,
    QgsAnnotationLayer,
    QgsCoordinateTransformContext,
    QgsDataSourceUri,
    QgsMapLayer,
    QgsMeshLayer,
    QgsPointCloudLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsTiledSceneLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorTileLayer,
)

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AnnotationLayerInfo,
    CanvasExtent,
    GeometryType,
    LayerInfo,
    MeshLayerInfo,
    PointCloudLayerInfo,
    QgisSdkExportFailedError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    TiledSceneLayerInfo,
    VectorExport,
    VectorLayerInfo,
    VectorTileLayerInfo,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no import cycle at runtime
    from .rasters import NativeRasters

GEOMETRY_TYPES: dict[int, GeometryType] = {
    Qgis.GeometryType.Point: "point",
    Qgis.GeometryType.Line: "line",
    Qgis.GeometryType.Polygon: "polygon",
}
NO_GEOMETRY: GeometryType = "none"
# These OGR drivers have a directly identifiable local dataset. Indirect
# providers (notably VRT) can refer to other files and must fail closed.
_LOCAL_SOURCE_DRIVERS = frozenset({"GeoJSON", "GPKG", "ESRI Shapefile"})

__all__ = ["NativeLayers"]


class NativeLayers:
    """Open local vector datasets through QGIS's own providers.

    Ownership: every layer this runtime opens is released when the owner scope
    closes, and every operation is refused afterwards rather than returning a
    stale reference (decision-20).
    """

    def __init__(
        self, scope: ResourceScope, *, rasters: NativeRasters | None = None
    ) -> None:
        self._scope = scope
        self._layers: dict[str, QgsVectorLayer] = {}
        #: The layers of the five other kinds this adapter opened (TASK-91), each
        #: with the description its kind answers, keyed by layer id. The PyQGIS
        #: handle is kept only so the scope can drop it with everything else.
        self._native_others: dict[str, QgsMapLayer] = {}
        self._others: dict[str, LayerInfo] = {}
        self._export_sources: dict[str, export_policy.SourceIdentity | None] = {}
        #: The sibling raster adapter, when the host built one: ``list_layers``
        #: answers both kinds and a raster id reaching a vector-only method is
        #: refused by name rather than reported as missing.
        self._rasters = rasters
        scope.on_close(self._release)

    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Open a local dataset with OGR and describe the resulting layer."""
        self._scope.ensure_open()
        layer = QgsVectorLayer(str(source), Path(source).stem, "ogr")
        if not layer.isValid():
            raise QgisSdkLayerNotFoundError(str(source))
        self._layers[layer.id()] = layer
        self._export_sources[layer.id()] = _capture_source(layer)
        return _describe(layer)

    def adopt_vector(self, layer: QgsVectorLayer) -> VectorLayerInfo:
        """Describe and register a vector layer another adapter opened.

        ``connections.open_layer`` (TASK-92) builds its layer from a provider
        connection's table URI rather than a file path; the description and the
        scope-owned registry stay this service's to own, so the layer lands here
        instead of a second registry growing beside it. The caller checked
        ``layer.isValid()`` and raised its own refusal.
        """
        self._scope.ensure_open()
        self._layers[layer.id()] = layer
        self._export_sources[layer.id()] = _capture_source(layer)
        return _describe(layer)

    def open_mesh(self, source: Path) -> MeshLayerInfo:
        """Open a mesh dataset and describe its vertices, faces and groups."""
        layer = QgsMeshLayer(str(source), Path(source).stem, "mdal")
        self._remember(layer)
        return _describe_mesh(layer)

    def open_point_cloud(self, source: Path) -> PointCloudLayerInfo:
        """Open a point cloud and describe its point count and attributes.

        ``pdal`` is the *metadata* key the point cloud provider registers with
        ``QgsProviderRegistry``; ``pointcloud`` is the name of its library and
        of the layer type, not something the registry answers to. A key it does
        not know is answered with no provider and an invalid layer, which reads
        as a broken file rather than as a wrong name - so the key is the one
        QGIS itself passes.
        """
        layer = QgsPointCloudLayer(str(source), Path(source).stem, "pdal")
        self._remember(layer)
        return _describe_point_cloud(layer)

    def open_vector_tile(self, source: Path) -> VectorTileLayerInfo:
        """Open a vector tile layer and describe its source type and zooms.

        A vector tile layer's data source is a ``QgsDataSourceUri``, not a file
        path: the layer reads ``type`` out of it to choose a provider, and the
        provider reads its own parameters out of the same string. An MBTiles file
        is therefore ``type=mbtiles&url=<path>``; a bare path carries no source
        type at all, and the layer comes back invalid with no provider.
        """
        layer = QgsVectorTileLayer(_vector_tile_source(source), Path(source).stem)
        self._remember(layer)
        return _describe_vector_tile(layer)

    def open_annotation(self, name: str) -> AnnotationLayerInfo:
        """Create an annotation layer of the project under ``name``.

        An annotation layer has no dataset: it is a drawing surface the project
        holds, so the name is the identity and a new one starts empty.

        ``LayerOptions`` takes the project's transform context and has no
        default constructor, which is the one thing a caller has to bring: an
        annotation layer is created *into* a project's coordinate world.
        """
        options = QgsAnnotationLayer.LayerOptions(
            QgsProject.instance().transformContext()
        )
        layer = QgsAnnotationLayer(name, options)
        self._remember(layer)
        return _describe_annotation(layer)

    def open_tiled_scene(self, source: Path) -> TiledSceneLayerInfo:
        """Open a 3D tiled scene and describe the box it occupies."""
        layer = QgsTiledSceneLayer(str(source), Path(source).stem, "cesiumtiles")
        self._remember(layer)
        return _describe_tiled_scene(layer)

    def list_layers(self) -> tuple[LayerInfo, ...]:
        """Return every opened layer, of every kind, in the order opened.

        Vector layers come first because they are the ones this adapter owns;
        the five other kinds follow in the order they were opened, and the
        rasters after them, in the order their own adapter opened them. A
        caller that needs one order reads the project's tree instead.
        """
        self._scope.ensure_open()
        opened: list[LayerInfo] = [_describe(layer) for layer in self._layers.values()]
        opened.extend(self._others.values())
        if self._rasters is not None:
            opened.extend(self._rasters.list_layers())
        return tuple(opened)

    def layer(self, layer_id: str) -> LayerInfo:
        """Return the description of one opened layer, of any kind."""
        self._scope.ensure_open()
        if layer_id in self._others:
            return self._others[layer_id]
        if layer_id not in self._layers and self._rasters is not None:
            return self._rasters.raster(layer_id)
        return _describe(self._require(layer_id))

    def selection(self, layer_id: str) -> tuple[int, ...]:
        """Return the layer's selected feature ids, unsorted by the provider."""
        self._scope.ensure_open()
        return tuple(self._require(layer_id).selectedFeatureIds())

    def export_vector(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> VectorExport:
        """Write the layer with ``QgsVectorFileWriter`` under the shared policy.

        The writer targets a staged path, so a GeoPackage journal or a
        half-written file never appears at the destination. The shared policy
        checks the source before writing and immediately before committing.
        """
        self._scope.ensure_open()
        layer = self._require(layer_id)
        plan = export_policy.plan_export(destination, overwrite=overwrite)
        plan = export_policy.protect_source(plan, self._export_sources[layer_id])
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = plan.driver
        options.fileEncoding = "UTF-8"

        def write(partial: Path) -> None:
            error, message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, str(partial), QgsCoordinateTransformContext(), options
            )
            if error != QgsVectorFileWriter.WriterError.NoError:
                raise QgisSdkExportFailedError(
                    str(plan.destination), message or f"writer error {error}"
                )

        export_policy.run_export(plan, write)
        return VectorExport(path=str(plan.destination), driver=plan.driver)

    def _qgs_layer(self, layer_id: str) -> QgsVectorLayer:
        """Hand the native handle to a sibling adapter in this package.

        Package-internal: this is the documented handoff between ``NativeLayers``
        and ``NativeProject``, which must add the very layer instance this
        adapter owns. Author and bridge code use the contract, never this.
        """
        self._scope.ensure_open()
        return self._require(layer_id)

    def _remember(self, layer: QgsMapLayer) -> None:
        """Refuse an invalid layer, otherwise remember it and its description.

        Every provider answers a layer that is invalid when it cannot read the
        dataset, so an unreadable file and a file of another kind are the same
        refusal: a layer this runtime does not have. The description is built
        here rather than by the caller so a layer is never remembered without
        the description ``layer()`` has to answer.
        """
        self._scope.ensure_open()
        if not layer.isValid():
            raise QgisSdkLayerNotFoundError(layer.source() or layer.name())
        self._native_others[layer.id()] = layer
        self._others[layer.id()] = _describe_other(layer)

    def _require(self, layer_id: str) -> QgsVectorLayer:
        try:
            return self._layers[layer_id]
        except KeyError:
            pass
        other = self._others.get(layer_id)
        if other is not None:
            raise QgisSdkUnsupportedCapabilityError(
                layer_id,
                f"this layer is a {other.kind}; fields, features, styles and a "
                "vector export are vector work - read it through the service its "
                "kind belongs to (ctx.rasters for a raster)",
            )
        if self._rasters is not None and self._rasters.knows(layer_id):
            raise QgisSdkUnsupportedCapabilityError(
                layer_id,
                "this layer is a raster; fields, features, styles and a vector "
                "export are vector work - read it through ctx.rasters",
            )
        raise QgisSdkLayerNotFoundError(layer_id)

    def _release(self) -> None:
        """Drop this runtime's references; the scope closes exactly once."""
        self._layers.clear()
        self._native_others.clear()
        self._others.clear()
        self._export_sources.clear()


def _is_local_path(path: object) -> bool:
    """Whether a decoded source names a path on this machine.

    A provider may answer no path at all, a relative one, or a URI -
    ``/vsizip//…`` and ``postgres://…`` alike - and none of those is a file this
    process may describe.
    """
    if not isinstance(path, str) or not path:
        return False
    return "://" not in path


def _capture_source(layer: QgsVectorLayer) -> export_policy.SourceIdentity | None:
    """Identify only qualified direct local datasets; leave others unexportable."""
    try:
        provider = layer.dataProvider()
        if (
            layer.providerType() != "ogr"
            or provider.storageType() not in _LOCAL_SOURCE_DRIVERS
        ):
            return None
        decoded = QgsProviderRegistry.instance().decodeUri(
            layer.providerType(), layer.source()
        )
        path = decoded.get("path")
        if not _is_local_path(path) or decoded.get("vsiPrefix"):
            return None
        return export_policy.capture_source(Path(path))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        # A source that cannot be decoded remains readable, but cannot be
        # exported because its physical dataset cannot be protected safely.
        return None


#: How a layer of another kind is described. Keyed by the PyQGIS class each
#: ``open_*`` method built, so the description a layer answers is chosen by what
#: the provider produced rather than by what the caller asked for.
_DESCRIBERS: dict[type, Callable[[QgsMapLayer], LayerInfo]] = {}


def _describe_other(layer: QgsMapLayer) -> LayerInfo:
    """Return the description a layer of any kind answers."""
    for layer_class, describe in _DESCRIBERS.items():
        if isinstance(layer, layer_class):
            return describe(layer)
    raise QgisSdkUnsupportedCapabilityError(
        layer.name(), f"{type(layer).__name__} is not a layer kind this SDK describes"
    )


def _authid(layer: QgsMapLayer) -> str | None:
    """The layer's authority code, or ``None`` when it has no CRS of its own."""
    return layer.crs().authid() or None


#: The vector tile source types this adapter opens, by file suffix. A vector tile
#: source is a container QGIS reads through its own provider, and the URI has to
#: name the type before the provider can decode the rest of it.
_VECTOR_TILE_SOURCE_TYPES = {".mbtiles": "mbtiles", ".vtpk": "vtpk"}


def _vector_tile_source(source: Path) -> str:
    """Return the data-source URI a vector tile layer reads for ``source``.

    Built with ``QgsDataSourceUri`` rather than by joining strings, because that
    is what percent-encodes the path once and decodes it once: a temp directory
    with a space in it must survive the round trip, and a path that carries ``&``
    must not become a second parameter.
    """
    suffix = Path(source).suffix.lower()
    source_type = _VECTOR_TILE_SOURCE_TYPES.get(suffix)
    if source_type is None:
        raise QgisSdkUnsupportedCapabilityError(
            Path(source).name,
            f"a {suffix or 'file with no suffix'} is not a vector tile source "
            f"this SDK opens; {', '.join(_VECTOR_TILE_SOURCE_TYPES)} are",
        )
    uri = QgsDataSourceUri()
    uri.setParam("type", source_type)
    uri.setParam("url", str(source))
    return bytes(uri.encodedUri()).decode()


def _describe_mesh(layer: QgsMeshLayer) -> MeshLayerInfo:
    """Translate a mesh layer into vertices, faces and dataset groups.

    The counts come from the provider, which reports zero for a dataset it has
    not read yet - an unread mesh is still a mesh this project holds, and a
    description that refused to answer would hide it from the layer list.
    """
    provider = layer.dataProvider()
    return MeshLayerInfo(
        id=layer.id(),
        name=layer.name(),
        crs=_authid(layer),
        vertex_count=int(provider.vertexCount()) if provider is not None else 0,
        face_count=int(provider.faceCount()) if provider is not None else 0,
        group_count=int(layer.datasetGroupCount()),
    )


def _describe_point_cloud(layer: QgsPointCloudLayer) -> PointCloudLayerInfo:
    """Translate a point cloud into its point total and attribute names.

    ``QgsPointCloudAttributeCollection`` counts with ``count()``: it is a
    ``QVector``-like container, not a Qt list, and it has no ``size()``.
    """
    attributes = layer.attributes()
    return PointCloudLayerInfo(
        id=layer.id(),
        name=layer.name(),
        crs=_authid(layer),
        point_count=int(layer.pointCount()),
        attribute_names=tuple(
            attributes.at(index).name() for index in range(attributes.count())
        ),
    )


def _describe_vector_tile(layer: QgsVectorTileLayer) -> VectorTileLayerInfo:
    """Translate a vector tile layer into its source type and zoom range."""
    return VectorTileLayerInfo(
        id=layer.id(),
        name=layer.name(),
        crs=_authid(layer),
        source_type=layer.sourceType(),
        min_zoom=int(layer.sourceMinZoom()),
        max_zoom=int(layer.sourceMaxZoom()),
    )


def _describe_annotation(layer: QgsAnnotationLayer) -> AnnotationLayerInfo:
    """Translate an annotation layer into how many items it holds."""
    return AnnotationLayerInfo(
        id=layer.id(),
        name=layer.name(),
        crs=_authid(layer),
        item_count=len(layer.items()),
    )


def _describe_tiled_scene(layer: QgsTiledSceneLayer) -> TiledSceneLayerInfo:
    """Translate a tiled scene into the box it occupies.

    A tiled scene has no cheap tile count: the provider reads one asynchronously
    and 3.44 has no synchronous total, so the description carries the extent
    rather than a number it would have to invent.
    """
    extent = layer.extent()
    return TiledSceneLayerInfo(
        id=layer.id(),
        name=layer.name(),
        crs=_authid(layer),
        extent=CanvasExtent(
            x_min=extent.xMinimum(),
            y_min=extent.yMinimum(),
            x_max=extent.xMaximum(),
            y_max=extent.yMaximum(),
            crs=None,
        ),
    )


_DESCRIBERS.update(
    {
        QgsMeshLayer: _describe_mesh,
        QgsPointCloudLayer: _describe_point_cloud,
        QgsVectorTileLayer: _describe_vector_tile,
        QgsAnnotationLayer: _describe_annotation,
        QgsTiledSceneLayer: _describe_tiled_scene,
    }
)


def _describe(layer: QgsVectorLayer) -> VectorLayerInfo:
    """Translate a native layer into the QGIS-free description."""
    crs = layer.crs().authid()
    return VectorLayerInfo(
        id=layer.id(),
        name=layer.name(),
        geometry_type=GEOMETRY_TYPES.get(layer.geometryType(), NO_GEOMETRY),
        field_names=tuple(layer.fields().names()),
        crs=crs or None,
    )
