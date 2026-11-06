"""PyQGIS-backed layer service.

Native module: importing it needs a QGIS installation, so nothing on the pure
side may import it (``tests/test_pure_imports.py`` guards that). The adapter
returns :class:`~qgis_sdk.models.layers.LayerInfo` values - a
:class:`~qgis_sdk.models.layers.VectorLayerInfo` or, when a sibling
``NativeRasters`` opened it, a
:class:`~qgis_sdk.models.layers.RasterLayerInfo` - and never a PyQGIS handle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsProviderRegistry,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    GeometryType,
    LayerInfo,
    QgisSdkExportFailedError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    VectorExport,
    VectorLayerInfo,
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

    def list_layers(self) -> tuple[LayerInfo, ...]:
        """Return every opened layer, of both kinds, in the order opened.

        Vector layers come first because they are the ones this adapter owns;
        the rasters follow in the order their own adapter opened them. A caller
        that needs one order reads the project's tree instead.
        """
        self._scope.ensure_open()
        opened: list[LayerInfo] = [_describe(layer) for layer in self._layers.values()]
        if self._rasters is not None:
            opened.extend(self._rasters.list_layers())
        return tuple(opened)

    def layer(self, layer_id: str) -> LayerInfo:
        """Return the description of one opened layer, of either kind."""
        self._scope.ensure_open()
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

    def _require(self, layer_id: str) -> QgsVectorLayer:
        try:
            return self._layers[layer_id]
        except KeyError:
            pass
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
        self._export_sources.clear()


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
        if (
            not isinstance(path, str)
            or not path
            or "://" in path
            or decoded.get("vsiPrefix")
        ):
            return None
        return export_policy.capture_source(Path(path))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        # A source that cannot be decoded remains readable, but cannot be
        # exported because its physical dataset cannot be protected safely.
        return None


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
