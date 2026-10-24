"""PyQGIS-backed layer service.

Native module: importing it needs a QGIS installation, so nothing on the pure
side may import it (``tests/test_pure_imports.py`` guards that). The adapter
returns ``VectorLayerInfo`` values only; ``QgsVectorLayer`` handles never cross
this boundary.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import Qgis, QgsVectorLayer

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    GeometryType,
    QgisSdkLayerNotFoundError,
    VectorLayerInfo,
)

GEOMETRY_TYPES: dict[int, GeometryType] = {
    Qgis.GeometryType.Point: "point",
    Qgis.GeometryType.Line: "line",
    Qgis.GeometryType.Polygon: "polygon",
}
NO_GEOMETRY: GeometryType = "none"

__all__ = ["NativeLayers"]


class NativeLayers:
    """Open local vector datasets through QGIS's own providers.

    Ownership: every layer this runtime opens is released when the owner scope
    closes, and every operation is refused afterwards rather than returning a
    stale reference (decision-20).
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._layers: dict[str, QgsVectorLayer] = {}
        scope.on_close(self._release)

    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Open a local dataset with OGR and describe the resulting layer."""
        self._scope.ensure_open()
        layer = QgsVectorLayer(str(source), Path(source).stem, "ogr")
        if not layer.isValid():
            raise QgisSdkLayerNotFoundError(str(source))
        self._layers[layer.id()] = layer
        return _describe(layer)

    def list_layers(self) -> tuple[VectorLayerInfo, ...]:
        """Return opened layers in the order they were opened."""
        self._scope.ensure_open()
        return tuple(_describe(layer) for layer in self._layers.values())

    def layer(self, layer_id: str) -> VectorLayerInfo:
        """Return the description of one opened layer."""
        self._scope.ensure_open()
        return _describe(self._require(layer_id))

    def selection(self, layer_id: str) -> tuple[int, ...]:
        """Return the layer's selected feature ids, unsorted by the provider."""
        self._scope.ensure_open()
        return tuple(self._require(layer_id).selectedFeatureIds())

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
            raise QgisSdkLayerNotFoundError(layer_id) from None

    def _release(self) -> None:
        """Drop this runtime's references; the scope closes exactly once."""
        self._layers.clear()


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
