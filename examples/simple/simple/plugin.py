"""Simple: the local GIS slice of decision-19 as one qgis-sdk plugin.

Five declared actions carry the whole workflow - open the fixture, read the
selection, buffer in an explicit projected CRS, export, choose where exports
go - one line lists the Processing provider the plugin owns
(:mod:`.algorithms`) and one the native window it opens (:mod:`.surfaces`);
nothing else is in this file: no Qt import, no QGIS import, no widget, no
``classFactory``. ``pyproject.toml`` names this app under
``[tool.qgis-sdk] plugin``; ``qgis-sdk build`` and ``qgis-sdk dev`` bind
QGIS's entry to it and open the page in ``web/`` as a dock (decision-43). The
``BufferDialog`` built from ``Form.for_action`` and that page are two front
ends over the same ``runtime.actions``, which is what "equivalent native and
web controls" means here.

The work itself is :class:`.workflow.LocalGisWorkflow`, the plugin's own
chain over the SDK services; this file adds what only a plugin declares -
the actions, where its fixture is and where its exports go.
"""

from __future__ import annotations

from pathlib import Path

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext
from qgis_sdk.models import (
    CrsInput,
    LayerInput,
    Metres,
    QgisSdkExportRefusedError,
    VectorExport,
    VectorLayerInfo,
)

from . import algorithms, dialogs, surfaces
from .workflow import LocalGisWorkflow

PLUGIN_ID = "simple"
TITLE = "Simple"

#: The local fixture dataset shipped inside the plugin package (decision-19: no
#: external service gates the reference workflow).
FIXTURE = Path(__file__).resolve().parent / "data" / "points.geojson"

#: The settings key holding the directory exports are written to. A page never
#: names a path (decision-20): it names a file *inside* this directory, and the
#: directory itself is chosen on the host - by a native folder picker here.
EXPORT_DIRECTORY_KEY = "export_directory"


app = QgisSdkPlugin(id=PLUGIN_ID, title=TITLE)
app.add_provider(algorithms.provider)
for surface in surfaces.surfaces:
    app.add_surface(surface)


@app.action(id="open_fixture", title="Open the fixture dataset")
def open_fixture(ctx: PluginContext) -> VectorLayerInfo:
    """Load the bundled points and add them to the project."""
    return LocalGisWorkflow(ctx).open_dataset(FIXTURE)


@app.action(id="selected_features", title="Selected features")
def selected_features(ctx: PluginContext, layer_id: LayerInput) -> list[int]:
    """Read the host's selection on a layer."""
    return sorted(LocalGisWorkflow(ctx).selected_features(layer_id))


@app.action(id="buffer", title="Buffer in a projected CRS")
def buffer(
    ctx: PluginContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Buffer a layer by metres inside ``working_crs``; style and present it."""
    return LocalGisWorkflow(ctx).buffer(layer_id, distance_metres, working_crs)


@app.action(id="export_layer", title="Export a layer")
def export_layer(
    ctx: PluginContext, layer_id: LayerInput, file_name: str, overwrite: bool = False
) -> VectorExport:
    """Write a layer inside the chosen export directory."""
    return LocalGisWorkflow(ctx).export(
        layer_id, _destination(ctx, file_name), overwrite=overwrite
    )


@app.action(id="choose_export_directory", title="Choose the export directory")
def choose_export_directory(ctx: PluginContext) -> str:
    """Ask the user for a directory through the Desktop and remember it."""
    chosen = dialogs.ask_for_directory(ctx.desktop.iface, TITLE)
    if not chosen:
        raise QgisSdkExportRefusedError("", ["no directory was chosen"])
    ctx.settings.set(EXPORT_DIRECTORY_KEY, chosen)
    return chosen


def _destination(ctx: PluginContext, file_name: str) -> Path:
    """Resolve a bare file name inside the configured export directory."""
    reasons: list[str] = []
    if not file_name or Path(file_name).name != file_name or file_name in (".", ".."):
        reasons.append("file_name must be a bare file name, not a path")
    directory = ctx.settings.get(EXPORT_DIRECTORY_KEY)
    if not directory:
        reasons.append(
            f"no export directory is set; run 'choose_export_directory' first "
            f"(settings key {EXPORT_DIRECTORY_KEY!r})"
        )
    if reasons:
        raise QgisSdkExportRefusedError(file_name, reasons)
    assert directory is not None
    return Path(directory) / file_name
