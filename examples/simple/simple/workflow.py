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
services and the reference *algorithms*; what a plugin chains them into is the
plugin's own code, and this file is the worked example of that. Nothing here
holds Qt or QGIS: the class is a consumer of the injected
:class:`~qgis_sdk.core.PluginContext`.
"""

from __future__ import annotations

from pathlib import Path

from qgis_sdk.algorithms import invoke
from qgis_sdk.core import PluginContext
from qgis_sdk.models import VectorExport, VectorLayerInfo
from qgis_sdk.reference import buffer_layer
from qgis_sdk.services import Cancellation, Progress

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
        *,
        progress: Progress | None = None,
        cancellation: Cancellation | None = None,
    ) -> VectorLayerInfo:
        """Buffer a layer in metres inside ``working_crs``; style, then present.

        The algorithm's request refuses an empty CRS, and the native service
        refuses a geographic or non-metre one, before anything is written.
        """
        output = invoke(
            buffer_layer,
            self.ctx,
            progress=progress,
            cancellation=cancellation,
            add_to_project=False,
            layer_id=layer_id,
            distance_metres=distance_metres,
            working_crs=working_crs,
        )
        self.ctx.styles.apply_style(output.id, self.OUTPUT_STYLE)
        self.ctx.project.add_layer(output.id)
        return output

    def export(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> VectorExport:
        """Write a layer to a file the caller named; explicit, never implied."""
        return self.ctx.layers.export_vector(
            layer_id, Path(destination), overwrite=overwrite
        )
