"""Simple: the local GIS slice of decision-19 as one qgis-sdk plugin.

Five declared actions carry the whole workflow - open the fixture, read the
selection, buffer in an explicit projected CRS, export, choose where exports
go - and one line lists the Processing provider the plugin owns
(:mod:`.algorithms`); nothing else is in this file: no Qt import, no QGIS
import, no widget, no ``classFactory``. ``pyproject.toml`` names this class
under ``[tool.qgis-sdk] plugin``; ``qgis-sdk build`` and ``qgis-sdk dev`` bind
QGIS's entry to it and open the page in ``web/`` as a dock (decision-43). The
native dialog QGIS shows for an action and that page are two front ends over
the same ``runtime.actions``, which is what "equivalent native and web
controls" means here.

The work itself is :class:`.workflow.LocalGisWorkflow`, the plugin's own
chain over the SDK services; this file adds what only a plugin declares -
the actions, where its fixture is and where its exports go.
"""

from __future__ import annotations

from pathlib import Path

from qgis_sdk import action, plugin
from qgis_sdk.core import PluginContext
from qgis_sdk.models import (
    CrsInput,
    LayerInput,
    Metres,
    QgisSdkExportRefusedError,
    VectorExport,
    VectorLayerInfo,
)

from . import algorithms, dialogs
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


@plugin(id=PLUGIN_ID, title=TITLE)
class SimplePlugin:
    """Declared actions only; the runtime binds ``ctx`` while the plugin runs."""

    ctx: PluginContext

    #: The plugin's algorithms appear in the toolbox as ``simple:buffer`` and
    #: ``simple:centroid`` while the plugin runs inside QGIS; over the fakes
    #: the same line registers nothing (decision-42). A tuple, because a
    #: mutable class attribute is what Ruff's RUF012 flags.
    providers = (algorithms.provider,)

    @property
    def workflow(self) -> LocalGisWorkflow:
        return LocalGisWorkflow(self.ctx)

    @action(id="open_fixture", title="Open the fixture dataset")
    def open_fixture(self) -> VectorLayerInfo:
        """Load the bundled points and add them to the project."""
        return self.workflow.open_dataset(FIXTURE)

    @action(id="selected_features", title="Selected features")
    def selected_features(self, layer_id: LayerInput) -> list[int]:
        """Read the host's selection on a layer; this plugin never sets one."""
        return sorted(self.workflow.selected_features(layer_id))

    @action(id="buffer", title="Buffer in a projected CRS")
    def buffer(
        self,
        layer_id: LayerInput,
        distance_metres: Metres,
        working_crs: CrsInput,
    ) -> VectorLayerInfo:
        """Buffer a layer by metres inside ``working_crs``; style and present it."""
        return self.workflow.buffer(layer_id, distance_metres, working_crs)

    @action(id="export_layer", title="Export a layer")
    def export_layer(
        self,
        layer_id: LayerInput,
        file_name: str,
        overwrite: bool = False,
    ) -> VectorExport:
        """Write a layer to ``file_name`` inside the chosen export directory.

        ``file_name`` is a bare name (``buffer.gpkg``): a separator or a parent
        reference is refused before anything is resolved, so neither surface
        can turn this action into a write anywhere on disk.
        """
        return self.workflow.export(
            layer_id, _destination(self.ctx, file_name), overwrite=overwrite
        )

    @action(id="choose_export_directory", title="Choose the export directory")
    def choose_export_directory(self) -> str:
        """Ask the user for a directory through the Desktop and remember it."""
        iface = self.ctx.desktop.iface
        chosen = dialogs.ask_for_directory(iface, TITLE)
        if not chosen:
            raise QgisSdkExportRefusedError("", ["no directory was chosen"])
        self.ctx.settings.set(EXPORT_DIRECTORY_KEY, chosen)
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
