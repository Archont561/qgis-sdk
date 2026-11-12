"""Layer description: translate PyQGIS layers into QGIS-free values."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsAnnotationLayer,
    QgsDataSourceUri,
    QgsMapLayer,
    QgsMeshLayer,
    QgsPointCloudLayer,
    QgsTiledSceneLayer,
    QgsVectorLayer,
    QgsVectorTileLayer,
)

from qgis_sdk.models import (
    AnnotationLayerInfo,
    CanvasExtent,
    GeometryType,
    LayerInfo,
    MeshLayerInfo,
    PointCloudLayerInfo,
    QgisSdkUnsupportedCapabilityError,
    TiledSceneLayerInfo,
    VectorLayerInfo,
    VectorTileLayerInfo,
)

__all__ = [
    "GEOMETRY_TYPES",
    "NO_GEOMETRY",
    "describe",
    "describe_other",
    "vector_tile_source",
]

GEOMETRY_TYPES: dict[int, GeometryType] = {
    Qgis.GeometryType.Point: "point",
    Qgis.GeometryType.Line: "line",
    Qgis.GeometryType.Polygon: "polygon",
}
NO_GEOMETRY: GeometryType = "none"


def describe(layer: QgsVectorLayer) -> VectorLayerInfo:
    """Translate a native layer into the QGIS-free description."""
    crs = layer.crs().authid()
    return VectorLayerInfo(
        id=layer.id(),
        name=layer.name(),
        geometry_type=GEOMETRY_TYPES.get(layer.geometryType(), NO_GEOMETRY),
        field_names=tuple(layer.fields().names()),
        crs=crs or None,
    )


#: How a layer of another kind is described. Keyed by the PyQGIS class each
#: ``open_*`` method built, so the description a layer answers is chosen by what
#: the provider produced rather than by what the caller asked for.
_DESCRIBERS: dict[type, Callable[[QgsMapLayer], LayerInfo]] = {}


def describe_other(layer: QgsMapLayer) -> LayerInfo:
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


def vector_tile_source(source: Path) -> str:
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
