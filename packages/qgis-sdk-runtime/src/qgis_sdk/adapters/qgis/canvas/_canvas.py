"""The canvas over a real ``QgsMapCanvas``: reading, changing, capture, themes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict, Unpack

from qgis.core import QgsMapLayer, QgsRectangle

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

from ._helpers import extent_of, project_theme_names
from ._tool import CaptureTool

if TYPE_CHECKING:  # pragma: no cover - typing only, the import is circular at runtime
    from qgis_sdk.adapters.qgis.layers import NativeLayers

__all__ = ["NativeCanvas"]


class _NativeCanvasMixin1:
    # -- reading ------------------------------------------------------------

    def extent(self) -> CanvasExtent:
        canvas = self._require()
        return extent_of(canvas.extent(), self._crs())

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
        names = tuple(project_theme_names())
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
        names = tuple(project_theme_names())
        if name not in names:
            raise QgisSdkThemeNotFoundError(name)
        canvas.setTheme(name)
        canvas.refresh()
        self._applied_theme = name
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
        tool = CaptureTool(canvas, shape, self._crs())
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
        """Follow the canvas's ``extentsChanged`` until the canceller runs."""
        canvas = self._require()
        state = {"live": True}

        def changed() -> None:
            if state["live"]:
                on_extent(self.extent())

        canvas.extentsChanged.connect(changed)

        def cancel() -> None:
            # Idempotent, and safe after the canvas went away: a second call, or
            # a call on a canvas QGIS already deleted, is nothing.
            if not state["live"]:
                return
            state["live"] = False
            try:
                canvas.extentsChanged.disconnect(changed)
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
        the same way rather than handed to a page that would look it up. A
        canvas that does not report its theme at all falls back to the one this
        adapter applied.
        """
        canvas = self._canvas
        getter = getattr(canvas, "mapTheme", None) if canvas is not None else None
        reported = getter() if callable(getter) else None
        if reported and reported in names:
            return str(reported)
        applied = self._applied_theme
        if applied and applied in names:
            return applied
        return None


class _NativeCanvasMixin2:
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

    def _finish_capture(self, tool: CaptureTool, geometry: Geometry) -> None:
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


class NativeCanvas(_NativeCanvasMixin1, _NativeCanvasMixin2):
    """The ``Canvas`` contract over one ``QgsMapCanvas``.

    ``canvas`` is resolved lazily from ``iface.mapCanvas()`` so a context built
    before QGIS hands out an interface still works once it does; a host with no
    canvas refuses every method by name. ``layers`` is what a zoom to a layer or
    a selection resolves through, so a page cannot name a layer the plugin never
    opened.
    """

    def __init__(self, scope: ResourceScope, **options: Unpack[_InitOptions1]) -> None:
        values = _InitValues1(**options)
        self._scope = scope
        self._layers = values.layers
        self._iface = values.iface
        self._canvas = values.canvas
        self._host = values.host
        #: The tool that was active before a capture installed its own, put back
        #: when the capture ends however it ends.
        self._previous_tool: object | None = None
        self._active_capture: CaptureTool | None = None
        #: The theme this adapter applied last. ``mapTheme`` is the truth where
        #: the host exposes it; this is what a canvas that cannot report one is
        #: drawn with.
        self._applied_theme: str | None = None


class _InitOptions1(TypedDict, total=False):
    layers: NativeLayers | None
    iface: object | None
    canvas: object | None
    host: Host | None


@dataclass(frozen=True, slots=True)
class _InitValues1:
    layers: NativeLayers | None = None
    iface: object | None = None
    canvas: object | None = None
    host: Host | None = None
