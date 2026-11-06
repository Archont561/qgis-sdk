"""Layer reads the reference workflow needs; not a ``QgsVectorLayer`` mirror.

The list is *kinded* (TASK-87 and TASK-91, decision-54 points 3 and 4): a project
holds seven kinds of layer, so :meth:`Layers.list_layers` answers all of them and
a caller narrows with ``info.kind``. Vector-only work - fields, features, styles,
editing, a vector export - stays here and refuses another kind by name rather
than failing somewhere deeper, and the per-kind reads live beside it:
:mod:`qgis_sdk.services.rasters` for cells and bands, and one open method here
per kind that answers the description that kind actually has.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from qgis_sdk.models.layers import (
    AnnotationLayerInfo,
    LayerInfo,
    MeshLayerInfo,
    PointCloudLayerInfo,
    TiledSceneLayerInfo,
    VectorExport,
    VectorLayerInfo,
    VectorTileLayerInfo,
)


class Layers(Protocol):
    """Open local datasets and read layer state.

    No method edits geometry or attributes: in-place editing, transactions and
    undo are out of scope for this slice (decision-19). The one write,
    :meth:`export_vector`, produces a *new* file the caller named and never
    touches the layer's own source. Implementations raise
    ``QgisSdkLayerNotFoundError`` for an unknown layer identifier or dataset,
    and ``QgisSdkUnsupportedCapabilityError`` when a vector-only method is asked
    about another kind: a raster, a mesh, a point cloud, a tile layer, an
    annotation layer or a tiled scene.
    """

    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Open a local vector dataset and return its description."""
        ...

    def open_mesh(self, source: Path) -> MeshLayerInfo:
        """Open a mesh dataset and return its geometry and dataset counts.

        A mesh carries quantities as dataset *groups*, so ``group_count`` is how
        many the provider declares; zero is a mesh with geometry and no results.
        """
        ...

    def open_point_cloud(self, source: Path) -> PointCloudLayerInfo:
        """Open a point cloud and return its point total and attributes.

        ``point_count`` is the size of the dataset, not of the current subset: a
        page showing a filtered view still needs to know what it is filtering.
        """
        ...

    def open_vector_tile(self, source: Path) -> VectorTileLayerInfo:
        """Open a vector tile source and return its type and zoom range.

        The source's path is deliberately *not* part of the answer - a tile URL
        routinely carries a token, and a description is read by pages, logs and
        bug reports. ``source_type`` says what shape of source it is.
        """
        ...

    def open_annotation(self, name: str) -> AnnotationLayerInfo:
        """Create an in-memory annotation layer called ``name`` and describe it.

        An annotation layer has no dataset: it is a bag of drawn items, so it is
        created rather than opened, and a fresh one holds nothing.
        """
        ...

    def open_tiled_scene(self, source: Path) -> TiledSceneLayerInfo:
        """Open a 3D tiled scene and return the box it occupies.

        A scene's tile count is a walk of its index rather than a field, so what
        the description carries is where the scene sits in its own CRS.
        """
        ...

    def list_layers(self) -> tuple[LayerInfo, ...]:
        """Return every layer this runtime has opened, in the order opened.

        Every kind: a vector layer is a
        :class:`~qgis_sdk.models.layers.VectorLayerInfo`, a raster a
        :class:`~qgis_sdk.models.layers.RasterLayerInfo`, and a mesh, a point
        cloud, a vector tile layer, an annotation layer or a tiled scene has its
        own description. Each carries its ``kind`` so a page draws one row per
        layer without asking twice.
        """
        ...

    def layer(self, layer_id: str) -> LayerInfo:
        """Return the description of one opened layer, of either kind."""
        ...

    def selection(self, layer_id: str) -> tuple[int, ...]:
        """Return selected feature ids; an empty tuple means nothing selected.

        A raster has no features, so its id raises
        ``QgisSdkUnsupportedCapabilityError`` naming the kind.
        """
        ...

    def export_vector(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> VectorExport:
        """Write an opened vector layer to ``destination`` as a permanent export.

        Explicit by construction (decision-19): the caller names the file, the
        format follows its suffix (``.geojson`` or ``.gpkg``), an existing file
        is replaced only with ``overwrite=True``, and a failure leaves no
        partial output - the policy in :mod:`qgis_sdk.exports`. Raises
        ``QgisSdkExportRefusedError`` if the destination aliases the source,
        the source cannot be verified, or overwrite was not granted; a staged
        export is checked again before commit. Native verification currently
        supports direct local GeoJSON, GeoPackage and ESRI Shapefile datasets;
        indirect and unverified providers are refused. Retargeted source
        symlinks or relative paths that resolve differently are also refused;
        reopen the layer using the intended source before exporting. Publishing
        without overwrite needs hard-link support on the destination filesystem.
        Concurrent external filesystem changes between the last check and
        commit are not excluded; callers must keep source and paths stable.
        Writer or commit failures raise ``QgisSdkExportFailedError``. A raster id
        is refused with ``QgisSdkUnsupportedCapabilityError``: rasters export
        through ``ctx.rasters``.
        """
        ...
