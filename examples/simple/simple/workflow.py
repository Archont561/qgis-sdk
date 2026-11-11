"""The local GIS reference workflow (decision-19) as one plain class.

Load a local vector dataset, read the host's selection, run one distance
operation in an explicit projected CRS, style the new output, present it, and
export it only when asked. The plugin's declared actions call these methods
one to one, and its web page calls those same actions through the bridge - so
"native and web behave the same" is a property of this class and the SDK
services behind it, proven once on the fakes and once on QGIS, not a claim
about two user interfaces.

The ordering is the safety story. :meth:`buffer` runs the operation into a new
layer (``invoke`` with ``add_to_project=False``), applies the packaged style to
that layer, and adds it to the project *last*: a refused request, a failed run,
a cancellation or an incompatible style all leave the project exactly as it
was, with the source untouched.

This class lives in the plugin, not in ``qgis_sdk``: the runtime ships the
services; the algorithms (:mod:`.algorithms`) and what a plugin chains them
into are the plugin's own code, and this file is the worked example of that. Nothing here
holds Qt or QGIS: the class is a consumer of the injected
:class:`~qgis_sdk.core.PluginContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Unpack

from qgis_sdk.algorithms import invoke
from qgis_sdk.core import PluginContext
from qgis_sdk.models import (
    CanvasPoint,
    LayoutExport,
    RasterLayerInfo,
    RasterSample,
    RasterStatistics,
    VectorExport,
    VectorLayerInfo,
    ZoomTarget,
)
from qgis_sdk.services import Cancellation, Progress

from .algorithms import buffer_layer


def _buffer_phase1(output, self):
    self.ctx.project.add_layer(output.id)
    # Present it where the user is looking. The canvas is a capability a host
    # may not have - a QGIS Server request has map settings, not a view - so
    # the workflow asks whether this runtime has one instead of assuming a
    # window it cannot see.
    if self.ctx.has("canvas"):
        self.ctx.canvas.zoom_to(ZoomTarget.layer(output.id))
    return output


__all__ = ["LocalGisWorkflow"]


class LocalGisWorkflow:
    """The reference workflow over one plugin context."""

    #: The reviewed packaged style the buffered output receives.
    OUTPUT_STYLE = "reference/polygon-output"

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def open_dataset(self, source: Path) -> VectorLayerInfo:
        """Open a local vector dataset and present it, so the user can select."""
        info = self.ctx.layers.open_vector(Path(source))
        self.ctx.project.add_layer(info.id)
        return info

    def selected_features(self, layer_id: str) -> tuple[int, ...]:
        """Read the host's current selection; the workflow never sets one."""
        return self.ctx.layers.selection(layer_id)

    def buffer(
        self,
        layer_id: str,
        distance_metres: float,
        working_crs: str,
        **options: Unpack[_BufferOptions1],
    ) -> VectorLayerInfo:
        """Buffer a layer in metres inside ``working_crs``; style, then present.

        The algorithm's request refuses an empty CRS, and the native service
        refuses a geographic or non-metre one, before anything is written.
        """
        values = _BufferValues1(**options)
        output = invoke(
            buffer_layer,
            self.ctx,
            progress=values.progress,
            cancellation=values.cancellation,
            add_to_project=False,
            layer_id=layer_id,
            distance_metres=distance_metres,
            working_crs=working_crs,
        )
        self.ctx.styles.apply_style(output.id, self.OUTPUT_STYLE)
        return _buffer_phase1(output, self)

    def open_raster(self, source: Path) -> RasterLayerInfo:
        """Open a local raster and present it: a raster is a layer too.

        The layers service lists both kinds and the project holds both, so a
        raster takes the same path a vector layer does - open, then add - and
        the answer is a :class:`RasterLayerInfo` with the bands the file
        declares rather than a vector layer's geometry and fields.
        """
        info = self.ctx.rasters.open_raster(Path(source))
        self.ctx.project.add_layer(info.id)
        return info

    def sample(self, layer_id: str, point: CanvasPoint) -> RasterSample:
        """Read every band where the user points.

        The point arrives in whatever CRS the caller's map is in; the service
        reprojects it and answers where it landed, so the plugin does not have
        to know the raster's CRS first. ``None`` for a value is a no-data cell
        or a point outside the raster - never a zero.
        """
        return self.ctx.rasters.sample(layer_id, point)

    def band_statistics(self, layer_id: str, band: int = 1) -> RasterStatistics:
        """What a band holds: minimum, maximum, mean, deviation and the counts."""
        return self.ctx.rasters.statistics(layer_id, band)

    def export(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> VectorExport:
        """Write a layer to a file the caller named; explicit, never implied."""
        return self.ctx.layers.export_vector(
            layer_id, Path(destination), overwrite=overwrite
        )

    def print_layout(
        self, name: str, destination: Path, *, overwrite: bool = False
    ) -> LayoutExport:
        """Write one of the project's print layouts to a PDF the caller named.

        The layout is the user's own work - a page composed in the print
        designer - so the workflow only asks which one by name and where the
        file goes. ``render`` is the blocking form: the caller here is an action
        that answers once, and the export job (``ctx.layouts.export``) is what a
        plugin uses when it wants a bar and a cancel button instead.
        """
        return self.ctx.layouts.render(
            name,
            format="pdf",
            destination=self.ctx.files.grant_file(
                Path(destination), operations=("write",), overwrite=overwrite
            ),
            overwrite=overwrite,
        )


class _BufferOptions1(TypedDict, total=False):
    progress: Progress | None
    cancellation: Cancellation | None


@dataclass(frozen=True, slots=True)
class _BufferValues1:
    progress: Progress | None = None
    cancellation: Cancellation | None = None
