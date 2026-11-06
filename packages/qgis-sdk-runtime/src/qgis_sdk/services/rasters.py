"""Raster reads: open one, describe it, measure a band, sample a point, export.

TASK-87 and decision-54 point 3. A raster is not a vector layer with different
fields - it has bands, per-band statistics and a pixel grid - so it is a service
of its own, and the layer service only reports *that* a raster exists
(``Layers.list_layers`` returns both kinds).

Three choices are deliberate.

*The export is a call, not a stream.* ``export_raster`` blocks until the file is
written, exactly as ``Layers.export_vector`` does, because a caller that wants
progress already has one mechanism for long work: a ``@job``. The host does not
expose it to a page - a page never supplies a filesystem destination
(decision-20) - and the deferral is recorded by name.

*Statistics are per band and asked for by number.* A band is ``1``-based, the
way QGIS and GDAL name it. Asking for band ``0`` or ``band_count + 1`` is a
mistake in the request and is refused by name, never answered with zeros.

*Sampling takes a point in a CRS the caller names.* A page's point arrives in
whatever CRS its map is in; leaving the reprojection to the caller means a
plugin has to know the raster's CRS before it can ask, so ``sample`` does it:
the point is transformed when ``crs`` differs from the raster's own, and the
answer carries the point where it landed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from qgis_sdk.models.canvas import CanvasPoint
from qgis_sdk.models.layers import (
    RasterExport,
    RasterLayerInfo,
    RasterSample,
    RasterStatistics,
)

__all__ = ["Rasters"]


class Rasters(Protocol):
    """Open local rasters and read their bands.

    Every method raises ``QgisSdkLayerNotFoundError`` for an id this runtime did
    not open (including a vector layer's id - a raster call is not a vector
    call), ``QgisSdkRasterBandError`` for a band outside ``1..band_count``, and
    ``QgisSdkUnsupportedCapabilityError`` on a host that cannot read rasters at
    all.
    """

    def open_raster(self, source: Path) -> RasterLayerInfo:
        """Open a local raster dataset and describe its bands."""
        ...

    def raster(self, layer_id: str) -> RasterLayerInfo:
        """Describe one opened raster."""
        ...

    def statistics(self, layer_id: str, band: int) -> RasterStatistics:
        """Compute one band's statistics over the whole raster."""
        ...

    def sample(
        self, layer_id: str, point: CanvasPoint, *, band: int | None = None
    ) -> RasterSample:
        """Read the value of every band (or one band) at ``point``.

        ``point.crs`` names the CRS the caller's numbers are in; a point with no
        CRS is read as being in the raster's own. A pixel that is no-data, or
        outside the raster, answers ``None`` for that band rather than a zero.
        """
        ...

    def export_raster(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> RasterExport:
        """Write an opened raster to ``destination`` under the export policy.

        The caller names the file, the format follows its suffix
        (:data:`~qgis_sdk.models.layers.RASTER_EXPORT_DRIVERS`), an existing
        file is replaced only with ``overwrite=True``, and a failure leaves no
        partial output - the same policy ``Layers.export_vector`` applies. Call
        it inside a ``@job``: it blocks for as long as the write takes.
        """
        ...
