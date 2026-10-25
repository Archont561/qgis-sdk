"""Simple: the local GIS slice of decision-19 as one qgis-sdk plugin.

Five declared actions carry the whole workflow - open the fixture, read the
selection, buffer in an explicit projected CRS, export, choose where exports
go - and nothing else is in this file: no Qt import, no QGIS import, no widget.
The native dialog QGIS shows for an action and the page in ``web/`` are two
front ends over the same ``runtime.actions``, which is what "equivalent native
and web controls" means here.

The work itself is :class:`.workflow.LocalGisWorkflow`, the plugin's own
chain over the SDK services; this file adds what only a plugin declares -
the actions, where its fixture is and where its exports go.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from qgis_sdk import action, plugin
from qgis_sdk.adapters.desktop import create_class_factory
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.models import (
    CrsInput,
    LayerInput,
    Metres,
    QgisSdkExportRefusedError,
    VectorExport,
    VectorLayerInfo,
)

from . import webview
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


class MessageBarNotifications:
    """Send informational messages to the host message bar, if there is one."""

    def __init__(self, iface: object | None) -> None:
        self._iface = iface

    def info(self, message: str) -> None:
        if self._iface is None:
            return
        self._iface.messageBar().pushInfo(TITLE, message)


@plugin(id=PLUGIN_ID, title=TITLE)
class SimplePlugin:
    """Declared actions only; the runtime binds ``ctx`` while the plugin runs."""

    ctx: PluginContext

    @property
    def workflow(self) -> LocalGisWorkflow:
        return LocalGisWorkflow(self.ctx)

    @action(id="open_fixture", title="Open the fixture dataset")
    def open_fixture(self) -> VectorLayerInfo:
        """Load the bundled points and add them to the project."""
        return self.workflow.open_dataset(FIXTURE)

    @action(id="selected_features", title="Selected features")
    def selected_features(self, layer_id: Annotated[str, LayerInput()]) -> list[int]:
        """Read the host's selection on a layer; this plugin never sets one."""
        return sorted(self.workflow.selected_features(layer_id))

    @action(id="buffer", title="Buffer in a projected CRS")
    def buffer(
        self,
        layer_id: Annotated[str, LayerInput()],
        distance_metres: Annotated[float, Metres()],
        working_crs: Annotated[str, CrsInput()],
    ) -> VectorLayerInfo:
        """Buffer a layer by metres inside ``working_crs``; style and present it."""
        return self.workflow.buffer(layer_id, distance_metres, working_crs)

    @action(id="export_layer", title="Export a layer")
    def export_layer(
        self,
        layer_id: Annotated[str, LayerInput()],
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
        chosen = webview.ask_for_directory(iface, TITLE)
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


def build_context(iface: object | None) -> PluginContext:
    """Give the plugin exactly the capabilities this host can offer.

    Inside a running QGIS every curated service is wired from PyQGIS; in a bare
    interpreter (the pure tests) the context carries notifications and a scope,
    and ``require_<service>()`` refuses by name instead of failing obscurely.
    """
    scope = ResourceScope()
    notifications = MessageBarNotifications(iface)
    if _qgis_is_running():
        from qgis_sdk.adapters.qgis import native_plugin_context

        return native_plugin_context(
            scope, settings_prefix=PLUGIN_ID, iface=iface, notifications=notifications
        )
    return PluginContext(notifications=notifications, scope=scope)


def _qgis_is_running() -> bool:
    try:
        from qgis.core import QgsApplication
    except ImportError:
        return False
    return QgsApplication.instance() is not None


_lifecycle = create_class_factory(SimplePlugin, context_factory=build_context)


class SimpleDesktop:
    """What QGIS holds: the SDK lifecycle plus one toolbar button for the page."""

    def __init__(self, iface: object | None) -> None:
        self._iface = iface
        self._plugin = _lifecycle(iface)
        self._action: object | None = None
        self._view: object | None = None

    @property
    def runtime(self) -> object:
        """The SDK runtime: the tests read it, the view's dispatcher is built from it."""
        return self._plugin.runtime

    def initGui(self) -> None:
        self._plugin.initGui()
        self._action = webview.add_toolbar_action(self._iface, TITLE, self.show_view)

    def show_view(self) -> None:
        """Open the page on first use; bring it to the front after that."""
        if self._view is None:
            self._view = webview.open_view(self.runtime, self._iface, placement="dock")
        self._view.show()
        self._view.raise_()

    def unload(self) -> None:
        if self._view is not None:
            webview.close_view(self._view, self._iface)
            self._view = None
        webview.remove_toolbar_action(self._iface, self._action)
        self._action = None
        self._plugin.unload()


def classFactory(iface: object | None) -> SimpleDesktop:
    """QGIS calls this with its interface; the tests call it with ``None``."""
    return SimpleDesktop(iface)
