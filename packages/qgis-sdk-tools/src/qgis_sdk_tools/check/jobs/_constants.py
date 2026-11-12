"""The worker-safety vocabulary: safe attributes, GUI paths, GUI classes."""

from __future__ import annotations

__all__ = ["GUI_CLASSES", "GUI_ONLY_PATHS", "WORKER_SAFE_ATTRIBUTES"]

#: What a ``WorkerContext`` carries; every other attribute is refused by name.
WORKER_SAFE_ATTRIBUTES = frozenset({"cancellation", "progress"})

#: Dotted paths that only mean something on the thread that owns the GUI.
GUI_ONLY_PATHS = frozenset(
    {
        "qgis.utils.iface",
        "qgis.gui.QgsInterface",
        "QgsProject.instance",
        "QgsApplication.activeWindow",
    }
)

#: Widget, canvas and interface classes: constructing or touching one from a
#: worker thread is a crash rather than a slow call. Matched on the last
#: segment of the resolved name, so an import alias is caught too. Deliberately
#: not every ``qgis.core`` class: reading a layer's data on a worker is a
#: documented hazard, not something a source check can call wrong.
GUI_CLASSES = frozenset(
    {
        # Qt
        "QApplication",
        "QDialog",
        "QDialogButtonBox",
        "QFileDialog",
        "QInputDialog",
        "QMainWindow",
        "QMessageBox",
        "QProgressDialog",
        "QWidget",
        # QGIS GUI
        "QgsDockWidget",
        "QgsFileWidget",
        "QgsGui",
        "QgsMapCanvas",
        "QgsMapCanvasItem",
        "QgsMapLayerComboBox",
        "QgsMapTool",
        "QgsMessageBar",
        "QgsOptionsDialogBase",
        "QgsProjectionSelectionWidget",
    }
)

_SDK_MODULES = frozenset({"qgis_sdk", "qgis_sdk.jobs", "qgis_sdk.declarations"})
_JOB_DECORATORS = frozenset(
    {"job", "qgis_sdk.job", "qgis_sdk.jobs.job", "qgis_sdk.declarations.job"}
)
_DYNAMIC_IMPORTS = frozenset({"importlib.import_module", "__import__"})


def is_gui_path(dotted: str) -> bool:
    """Whether a resolved dotted path is GUI state or a GUI class."""
    if any(dotted == item or dotted.endswith(f".{item}") for item in GUI_ONLY_PATHS):
        return True
    return dotted.rpartition(".")[2] in GUI_CLASSES
