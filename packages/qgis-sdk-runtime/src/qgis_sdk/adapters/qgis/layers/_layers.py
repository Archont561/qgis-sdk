"""PyQGIS-backed layer service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qgis.core import (
    QgsAnnotationLayer,
    QgsCoordinateTransformContext,
    QgsMapLayer,
    QgsMeshLayer,
    QgsPointCloudLayer,
    QgsProject,
    QgsTiledSceneLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorTileLayer,
)

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AnnotationLayerInfo,
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

from ._describe import describe, describe_other, vector_tile_source
from ._source import capture_source

if TYPE_CHECKING:  # pragma: no cover - typing only, no import cycle at runtime
    from qgis_sdk.adapters.qgis.rasters import NativeRasters

__all__ = ["NativeLayers"]


class _NativeLayersMixin1:
    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Open a local dataset with OGR and describe the resulting layer."""
        self._scope.ensure_open()
        layer = QgsVectorLayer(str(source), Path(source).stem, "ogr")
        if not layer.isValid():
            raise QgisSdkLayerNotFoundError(str(source))
        self._layers[layer.id()] = layer
        self._export_sources[layer.id()] = capture_source(layer)
        return describe(layer)

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
        self._export_sources[layer.id()] = capture_source(layer)
        return describe(layer)

    def open_mesh(self, source: Path) -> MeshLayerInfo:
        """Open a mesh dataset and describe its vertices, faces and groups."""
        layer = QgsMeshLayer(str(source), Path(source).stem, "mdal")
        self._remember(layer)
        return describe_other(layer)

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
        return describe_other(layer)

    def open_vector_tile(self, source: Path) -> VectorTileLayerInfo:
        """Open a vector tile layer and describe its source type and zooms.

        A vector tile layer's data source is a ``QgsDataSourceUri``, not a file
        path: the layer reads ``type`` out of it to choose a provider, and the
        provider reads its own parameters out of the same string. An MBTiles file
        is therefore ``type=mbtiles&url=<path>``; a bare path carries no source
        type at all, and the layer comes back invalid with no provider.
        """
        layer = QgsVectorTileLayer(vector_tile_source(source), Path(source).stem)
        self._remember(layer)
        return describe_other(layer)

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
        return describe_other(layer)

    def open_tiled_scene(self, source: Path) -> TiledSceneLayerInfo:
        """Open a 3D tiled scene and describe the box it occupies."""
        layer = QgsTiledSceneLayer(str(source), Path(source).stem, "cesiumtiles")
        self._remember(layer)
        return describe_other(layer)

    def list_layers(self) -> tuple[LayerInfo, ...]:
        """Return every opened layer, of every kind, in the order opened.

        Vector layers come first because they are the ones this adapter owns;
        the five other kinds follow in the order they were opened, and the
        rasters after them, in the order their own adapter opened them. A
        caller that needs one order reads the project's tree instead.
        """
        self._scope.ensure_open()
        opened: list[LayerInfo] = [describe(layer) for layer in self._layers.values()]
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
        return describe(self._require(layer_id))

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
        self._others[layer.id()] = describe_other(layer)


class _NativeLayersMixin2:
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


class NativeLayers(_NativeLayersMixin1, _NativeLayersMixin2):
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
