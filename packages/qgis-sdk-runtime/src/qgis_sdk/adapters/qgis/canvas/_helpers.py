"""Small helpers: mouse buttons, extents, and project theme names."""

from __future__ import annotations

from typing import Any

from qgis.core import QgsProject, QgsRectangle
from qgis.PyQt.QtCore import Qt

from qgis_sdk.models.canvas import CanvasExtent

__all__ = ["extent_of", "mouse_button", "project_theme_names"]


def mouse_button(name: str) -> Any:
    """One mouse button, spelled for the binding this QGIS uses.

    PyQt5 exposes ``Qt.LeftButton`` and PyQt6 nests them under ``Qt.MouseButton``;
    the adapter compares by value so it works on both, which is what lets the
    same file run on 3.44 and on a Qt 6 build.
    """
    enum = getattr(Qt, "MouseButton", Qt)
    return getattr(enum, name)


def extent_of(rectangle: QgsRectangle, crs: str | None) -> CanvasExtent:
    """Read a ``QgsRectangle`` as the wire extent, refusing an unordered one."""
    return CanvasExtent(
        x_min=rectangle.xMinimum(),
        y_min=rectangle.yMinimum(),
        x_max=rectangle.xMaximum(),
        y_max=rectangle.yMaximum(),
        crs=crs,
    )


def project_theme_names() -> list[str]:
    """The project's map theme names, in the collection's order."""
    collection = QgsProject.instance().mapThemeCollection()
    return [str(name) for name in collection.mapThemes()]
