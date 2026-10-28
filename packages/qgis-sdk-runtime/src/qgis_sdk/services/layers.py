"""Layer reads the reference workflow needs; not a ``QgsVectorLayer`` mirror."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from qgis_sdk.models import VectorExport, VectorLayerInfo


class Layers(Protocol):
    """Open local vector datasets and read layer state.

    No method edits geometry or attributes: in-place editing, transactions and
    undo are out of scope for this slice (decision-19). The one write,
    :meth:`export_vector`, produces a *new* file the caller named and never
    touches the layer's own source. Implementations raise
    ``QgisSdkLayerNotFoundError`` for an unknown layer identifier or dataset.
    """

    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Open a local vector dataset and return its description."""
        ...

    def list_layers(self) -> tuple[VectorLayerInfo, ...]:
        """Return every layer this runtime has opened, in the order opened."""
        ...

    def layer(self, layer_id: str) -> VectorLayerInfo:
        """Return the description of one opened layer."""
        ...

    def selection(self, layer_id: str) -> tuple[int, ...]:
        """Return selected feature ids; an empty tuple means nothing selected."""
        ...

    def export_vector(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> VectorExport:
        """Write an opened layer to ``destination`` as a permanent export.

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
        Writer or commit failures raise ``QgisSdkExportFailedError``.
        """
        ...
