"""The map canvas over a real ``QgsMapCanvas``, and the tool that draws on it.

One class answers the ``Canvas`` Protocol on a Desktop host, an app window and a
standalone ``QgsApplication``, and refuses on a server.

*There is no canvas on a server.* QGIS Server builds a ``QgsMapSettings`` per
request from the ``MAP=`` parameter; nothing there is a view a user pans. Rather
than synthesise an extent from the last request - which would answer "where is
the map" with a question somebody else asked - every method raises
``QgisSdkUnsupportedCapabilityError`` naming the host (decision-54 status review).

*Capture is a map tool, not a modal loop.* A drawing takes as long as a person
takes, so :meth:`NativeCanvas.capture` installs a ``QgsMapTool`` and returns; the
tool calls back when the geometry is finished and restores whatever tool was
active before. Cancelling puts the previous tool back without a callback. The
tool is a plain ``QgsMapTool`` subclass collecting ``canvasClicked`` points
rather than ``QgsMapToolCapture``: the latter brings snapping and the advanced
digitising dock, which are interactive features this service does not expose and
would make the offscreen test depend on a CAD dock that does not exist there.

*Themes come from the project, applied through the canvas.* ``QgsMapCanvas``
reports the theme it is drawn with, and the project owns the collection, so a
theme list and the active name are one answer read from two places.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from qgis.core import (
    QgsGeometry,
    QgsMapLayer,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import Qt, pyqtSignal

from qgis_sdk.core import Host, ResourceScope
from qgis_sdk.models.canvas import (
    CAPTURE_SHAPES,
    CanvasExtent,
    CanvasPoint,
    MapThemes,
    ZoomTarget,
)
from qgis_sdk.models.errors import (
    QgisSdkThemeNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.features import Geometry

from .features import _encode

if TYPE_CHECKING:  # pragma: no cover - typing only, the import is circular at runtime
    from .layers import NativeLayers

__all__ = ["NativeCanvas"]


def _mouse_button(name: str) -> Any:
    """One mouse button, spelled for the binding this QGIS uses.

    PyQt5 exposes ``Qt.LeftButton`` and PyQt6 nests them under ``Qt.MouseButton``;
    the adapter compares by value so it works on both, which is what lets the
    same file run on 3.44 and on a Qt 6 build.
    """
    enum = getattr(Qt, "MouseButton", Qt)
    return getattr(enum, name)


def _extent_of(rectangle: QgsRectangle, crs: str | None) -> CanvasExtent:
    """Read a ``QgsRectangle`` as the wire extent, refusing an unordered one."""
    return CanvasExtent(
        x_min=rectangle.xMinimum(),
        y_min=rectangle.yMinimum(),
        x_max=rectangle.xMaximum(),
        y_max=rectangle.yMaximum(),
        crs=crs,
    )


class NativeCanvas:
    """The ``Canvas`` contract over one ``QgsMapCanvas``.

    ``canvas`` is resolved lazily from ``iface.mapCanvas()`` so a context built
    before QGIS hands out an interface still works once it does; a host with no
    canvas refuses every method by name. ``layers`` is what a zoom to a layer or
    a selection resolves through, so a page cannot name a layer the plugin never
    opened.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        layers: NativeLayers | None = None,
        iface: object | None = None,
        canvas: object | None = None,
        host: Host | None = None,
    ) -> None:
        self._scope = scope
        self._layers = layers
        self._iface = iface
        self._canvas = canvas
        self._host = host
        #: The tool that was active before a capture installed its own, put back
        #: when the capture ends however it ends.
        self._previous_tool: object | None = None
        self._active_capture: _CaptureTool | None = None

    # -- reading ------------------------------------------------------------

    def extent(self) -> CanvasExtent:
        canvas = self._require()
        return _extent_of(canvas.extent(), self._crs())

    def scale(self) -> float:
        return float(self._require().scale())

    def crs(self) -> str | None:
        self._require()
        return self._crs()

    def center(self) -> CanvasPoint:
        point = self._require().center()
        return CanvasPoint(x=point.x(), y=point.y(), crs=self._crs())

    def themes(self) -> MapThemes:
        self._require()
        names = tuple(_project_theme_names())
        return MapThemes(names=names, active=self._active_theme(names))

    # -- changing -----------------------------------------------------------

    def zoom_to(self, target: ZoomTarget) -> CanvasExtent:
        canvas = self._require()
        rectangle = self._target_rectangle(target)
        if target.margin:
            # ``QgsRectangle.scale`` grows about the centre, so a margin of
            # ``m`` on every side is a factor of ``1 + 2m`` - the same
            # arithmetic ``FakeCanvas`` does, which is why the two backends
            # answer the same box for the same request.
            rectangle = QgsRectangle(rectangle)
            rectangle.scale(1.0 + 2.0 * target.margin)
        canvas.setExtent(rectangle)
        canvas.refresh()
        return self.extent()

    def refresh(self) -> None:
        self._require().refresh()

    def apply_theme(self, name: str) -> MapThemes:
        canvas = self._require()
        names = tuple(_project_theme_names())
        if name not in names:
            raise QgisSdkThemeNotFoundError(name)
        canvas.setTheme(name)
        canvas.refresh()
        return MapThemes(names=names, active=self._active_theme(names))

    # -- capture and the extent stream --------------------------------------

    def capture(
        self, shape: str, on_capture: Callable[[Geometry], None]
    ) -> Callable[[], None]:
        """Install a capture tool of ``shape`` and answer ``on_capture`` once.

        The previous tool is restored when the drawing finishes or is cancelled,
        so a plugin that had its own tool active gets it back rather than a dead
        canvas. A second capture replaces the first, cancelling it.
        """
        if shape not in CAPTURE_SHAPES:
            raise QgisSdkUnsupportedCapabilityError(
                f"{shape!r} is not a capture shape; draw one of "
                f"{', '.join(CAPTURE_SHAPES)}"
            )
        canvas = self._require()
        self._cancel_capture()
        tool = _CaptureTool(canvas, shape, self._crs())
        tool.finished.connect(lambda geometry: self._finish_capture(tool, geometry))
        tool.cancelled.connect(lambda: self._cancel_capture())
        self._previous_tool = canvas.mapTool()
        self._active_capture = tool
        tool.on_captured(on_capture)
        canvas.setMapTool(tool)

        def cancel() -> None:
            self._cancel_capture()

        return cancel

    def watch_extent(
        self, on_extent: Callable[[CanvasExtent], None]
    ) -> Callable[[], None]:
        """Follow ``extentChanged`` until the returned canceller runs."""
        canvas = self._require()
        state = {"live": True}

        def changed() -> None:
            if state["live"]:
                on_extent(self.extent())

        canvas.extentChanged.connect(changed)

        def cancel() -> None:
            # Idempotent, and safe after the canvas went away: a second call, or
            # a call on a canvas QGIS already deleted, is nothing.
            if not state["live"]:
                return
            state["live"] = False
            try:
                canvas.extentChanged.disconnect(changed)
            except (TypeError, RuntimeError):  # pragma: no cover - Qt lifetime race
                pass

        return cancel

    # -- internals ----------------------------------------------------------

    def _require(self) -> Any:
        """Return the canvas, refusing by name when this host has none."""
        if self._host is Host.SERVER:
            raise QgisSdkUnsupportedCapabilityError(
                "canvas: a QGIS Server request has map settings, not a map canvas"
            )
        if self._canvas is None and self._iface is not None:
            self._canvas = getattr(self._iface, "mapCanvas", lambda: None)()
        if self._canvas is None:
            raise QgisSdkUnsupportedCapabilityError(
                "canvas: this runtime has no map canvas; pass the QGIS interface "
                "or open an application window"
            )
        self._scope.ensure_open()
        return self._canvas

    def _crs(self) -> str | None:
        canvas = self._canvas
        if canvas is None:
            return None
        settings = getattr(canvas, "mapSettings", lambda: None)()
        crs = None if settings is None else settings.destinationCrs()
        return None if crs is None or crs.authid() == "" else crs.authid()

    def _active_theme(self, names: Sequence[str]) -> str | None:
        """The theme the canvas reports, or ``None`` when it reports nothing.

        Read through ``getattr`` because an empty project answers with an empty
        string and a canvas built without a theme answers with nothing at all;
        both are "no theme", and a name the project does not carry is treated
        the same way rather than handed to a page that would look it up.
        """
        canvas = self._canvas
        getter = getattr(canvas, "mapTheme", None) if canvas is not None else None
        reported = getter() if callable(getter) else None
        if not reported or reported not in names:
            return None
        return str(reported)

    def _target_rectangle(self, target: ZoomTarget) -> QgsRectangle:
        if target.kind == "extent":
            assert target.extent is not None  # refused by ZoomTarget itself
            return QgsRectangle(
                target.extent.x_min,
                target.extent.y_min,
                target.extent.x_max,
                target.extent.y_max,
            )
        layer = self._layer(str(target.layer_id))
        if target.kind == "selection":
            selected = layer.boundingBoxOfSelected()
            if selected.isNull() or selected.isEmpty():
                raise QgisSdkUnsupportedCapabilityError(
                    f"nothing is selected in layer {target.layer_id!r}, so there "
                    "is nothing to zoom to"
                )
            return selected
        extent = layer.extent()
        if extent.isNull() or extent.isEmpty():
            extent = layer.sourceExtent()
        if extent.isNull() or extent.isEmpty():
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {target.layer_id!r} has no extent to zoom to"
            )
        return extent

    def _layer(self, layer_id: str) -> QgsMapLayer:
        if self._layers is None:
            raise QgisSdkUnsupportedCapabilityError(
                "canvas: this runtime has no layer service, so it cannot resolve "
                f"layer {layer_id!r}"
            )
        return self._layers._qgs_layer(layer_id)

    def _finish_capture(self, tool: _CaptureTool, geometry: Geometry) -> None:
        if self._active_capture is not tool:
            return
        self._restore_tool()
        tool.deliver(geometry)

    def _cancel_capture(self) -> None:
        tool = self._active_capture
        if tool is None:
            return
        self._restore_tool()

    def _restore_tool(self) -> None:
        tool = self._active_capture
        self._active_capture = None
        canvas = self._canvas
        if tool is not None and canvas is not None:
            if self._previous_tool is None:
                canvas.unsetMapTool(tool)
            else:
                canvas.setMapTool(self._previous_tool)
        self._previous_tool = None


class _CaptureTool(QgsMapTool):
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
        if button is not None and button != _mouse_button("LeftButton"):
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
        geometry = self.geometry()
        if geometry is None or geometry.isEmpty():
            return
        self.finished.emit(_encode(geometry, "wkt", self._crs))


def _project_theme_names() -> list[str]:
    """The project's map theme names, in the collection's order."""
    collection = QgsProject.instance().mapThemeCollection()
    return [str(name) for name in collection.mapThemes()]
