"""The capture tool: collect map clicks into one geometry and hand it back."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis.core import QgsGeometry, QgsPointXY
from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import Qt, pyqtSignal

from qgis_sdk.models.features import Geometry

from ._helpers import mouse_button

__all__ = ["CaptureTool"]


class CaptureTool(QgsMapTool):
    """Collects map clicks into one point, line or polygon and hands it back.

    Clicks are appended in the order the user made them. A point finishes on the
    first click; a line or a polygon finishes when the user clicks the last
    vertex twice, which is what a double click looks like as two clicks on the
    same coordinates - the same gesture QGIS's own capture tool uses for "stop
    here". Escape cancels through ``keyPressEvent``.

    ``finished`` carries the ``Geometry`` the user drew, already encoded, so the
    caller never sees a ``QgsGeometry`` and the tool cannot leak one into a view.
    """

    #: The drawn geometry, encoded; emitted once per finished drawing.
    finished = pyqtSignal(object)
    #: The user abandoned the drawing (Escape), so nothing is delivered.
    cancelled = pyqtSignal()

    def __init__(self, canvas: Any, shape: str, crs: str | None) -> None:
        super().__init__(canvas)
        self._shape = shape
        self._crs = crs
        self._points: list[QgsPointXY] = []
        self._on_capture: Callable[[Geometry], None] | None = None
        self._delivered = False

    # -- what the canvas calls ----------------------------------------------

    def canvasClicked(self, point: QgsPointXY, button: Any = None) -> None:
        """One click: add a vertex, or finish when the gesture says so."""
        if button is not None and button != mouse_button("LeftButton"):
            return
        if self._shape == "point":
            self._points = [QgsPointXY(point)]
            self._finish()
            return
        if (
            self._shape == "polygon"
            and len(self._points) >= 3
            and point == self._points[0]
        ):
            # Clicking the first vertex again closes the ring.
            self._finish()
            return
        if len(self._points) >= 2 and point == self._points[-1]:
            # A second click on the same spot is the double click that ends a line.
            self._finish()
            return
        self._points.append(QgsPointXY(point))

    def keyPressEvent(self, event: Any) -> None:
        """Escape cancels the drawing; anything else is the canvas's business."""
        escape = getattr(Qt, "Key", Qt).Key_Escape
        if event is not None and event.key() == escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)

    # -- what the adapter uses ----------------------------------------------

    def on_captured(self, callback: Callable[[Geometry], None]) -> None:
        """Remember who to answer; the tool itself never calls back twice."""
        self._on_capture = callback

    def deliver(self, geometry: Geometry) -> None:
        """Hand the drawn geometry to the caller, once."""
        if self._delivered:
            return
        self._delivered = True
        callback = self._on_capture
        if callback is not None:
            callback(geometry)

    def geometry(self) -> QgsGeometry | None:
        """The geometry the collected points describe, or ``None`` so far."""
        points = list(self._points)
        if not points:
            return None
        if self._shape == "point":
            return QgsGeometry.fromPointXY(points[0])
        if self._shape == "line":
            return QgsGeometry.fromPolylineXY(points) if len(points) >= 2 else None
        if len(points) < 3:
            return None
        ring = [*points]
        if ring[0] != ring[-1]:
            ring.append(QgsPointXY(ring[0]))
        return QgsGeometry.fromPolygonXY([ring])

    def _finish(self) -> None:
        from qgis_sdk.adapters.qgis.features._geometry import encode as _encode

        geometry = self.geometry()
        if geometry is None or geometry.isEmpty():
            return
        self.finished.emit(_encode(geometry, "wkt", self._crs))
