"""An in-memory ``Canvas`` backend: extents, themes, capture and the extent stream.

The fake exists so the canvas contract is exercised without QGIS, and it is
honest about what it is: no map is drawn, so there is no projection to reproject
and no renderer to theme. What it *does* model is the part the contract is about
- the arithmetic of a zoom target, the refusal that names a layer with no extent
or nothing selected, a theme list whose active entry is always one of its own, a
capture session a test finishes with :meth:`FakeCanvas.draw`, and the callback
order an extent subscription promises.

Three rules make it a contract rather than a convenience.

*It knows nothing it was not told.* A layer's extent and a layer's selection are
declared by the test (``layer_extents``, :meth:`FakeCanvas.select`); a zoom to a
layer that was never declared refuses by name instead of zooming somewhere
plausible. A fake that invented an extent would let a test pass that the native
adapter cannot.

*Every state change is visible.* ``extent()`` after ``zoom_to`` is the extent the
zoom reported, an applied theme is the active one, and :attr:`FakeCanvas.refreshes`
counts redraws so a test can assert a call did not redraw rather than inferring it.

*A cancelled capture never calls back.* The canceller a page gets is the one the
host calls on dispose, and a session that called back after that would be a call
into a closed view.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from qgis_sdk.core import ResourceScope
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

__all__ = ["DEFAULT_EXTENT", "FakeCanvas"]

#: The extent a fake canvas starts on: a box around Lublin, in WGS 84. Arbitrary,
#: fixed and not magic - a test that needs another one sets it.
DEFAULT_EXTENT = CanvasExtent(
    x_min=22.4, y_min=51.1, x_max=22.7, y_max=51.35, crs="EPSG:4326"
)


@dataclass(slots=True)
class _CaptureSession:
    """One open capture: the shape asked for and the callback to answer."""

    shape: str
    on_capture: Callable[[Geometry], None]
    #: Set once the session is finished or cancelled; a second finish is inert.
    done: bool = False


@dataclass(slots=True)
class _ExtentSubscription:
    """One open extent subscription."""

    on_extent: Callable[[CanvasExtent], None]
    live: bool = True


class FakeCanvas:
    """A ``Canvas`` over a rectangle the test controls.

    ``layer_extents`` declares what ``zoom_to(ZoomTarget.layer(...))`` lands on,
    keyed by the layer id the layers service also knows; ``themes`` seeds the
    project's theme list. A selection is declared with :meth:`select`, because
    "zoom to selection" with nothing selected is a refusal the contract has to
    produce on both backends.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        extent: CanvasExtent = DEFAULT_EXTENT,
        layer_extents: Mapping[str, CanvasExtent] | None = None,
        themes: tuple[str, ...] = (),
        active_theme: str | None = None,
    ) -> None:
        self._scope = scope
        self._extent = extent
        self._layer_extents = dict(layer_extents or {})
        self._selections: dict[str, CanvasExtent] = {}
        self._theme_names = list(themes)
        self._active_theme = active_theme
        self._captures: list[_CaptureSession] = []
        self._subscriptions: list[_ExtentSubscription] = []
        self._drawn: list[Geometry] = []
        self.refreshes = 0

    # -- reading ------------------------------------------------------------

    def extent(self) -> CanvasExtent:
        self._scope.ensure_open()
        return self._extent

    def scale(self) -> float:
        """The scale denominator, derived from the extent so it moves with it.

        A fixed number would let a test assert a zoom that never happened; this
        is the extent's width over a nominal 0.0005 degrees per pixel, which
        changes whenever the extent does and claims nothing about cartography.
        """
        self._scope.ensure_open()
        return self._extent.width / 0.0005

    def crs(self) -> str | None:
        self._scope.ensure_open()
        return self._extent.crs

    def center(self) -> CanvasPoint:
        self._scope.ensure_open()
        return CanvasPoint(
            x=(self._extent.x_min + self._extent.x_max) / 2,
            y=(self._extent.y_min + self._extent.y_max) / 2,
            crs=self._extent.crs,
        )

    def themes(self) -> MapThemes:
        self._scope.ensure_open()
        return MapThemes(names=tuple(self._theme_names), active=self._active_theme)

    # -- changing -----------------------------------------------------------

    def zoom_to(self, target: ZoomTarget) -> CanvasExtent:
        """Move onto ``target`` and report where the canvas landed.

        An ``extent`` target is taken as given; a ``layer`` target uses the
        extent the test declared for that layer, and a ``selection`` target the
        box :meth:`select` recorded. Everything else refuses by name - the same
        refusal, in the same words, that the native adapter produces for a layer
        with no extent or nothing selected.
        """
        self._scope.ensure_open()
        landed = self._resolve(target)
        self._extent = landed
        self.refreshes += 1
        self._notify(landed)
        return landed

    def refresh(self) -> None:
        self._scope.ensure_open()
        self.refreshes += 1

    def apply_theme(self, name: str) -> MapThemes:
        self._scope.ensure_open()
        if name not in self._theme_names:
            raise QgisSdkThemeNotFoundError(name)
        self._active_theme = name
        self.refreshes += 1
        return self.themes()

    # -- capture and the extent stream --------------------------------------

    def capture(
        self, shape: str, on_capture: Callable[[Geometry], None]
    ) -> Callable[[], None]:
        """Start a capture session the test finishes with :meth:`draw`."""
        self._scope.ensure_open()
        _refuse_unknown_shape(shape)
        # One drawing at a time: a second capture replaces the first, exactly as
        # the native adapter swaps one map tool for another, so a test cannot
        # pass on a fake that stacks sessions the real canvas would have dropped.
        for open_session in self._captures:
            open_session.done = True
        self._captures.clear()
        session = _CaptureSession(shape=shape, on_capture=on_capture)
        self._captures.append(session)

        def cancel() -> None:
            # Ends the session without a callback, and drops it, so "is anything
            # being drawn" is a question the fake can answer afterwards.
            session.done = True
            if session in self._captures:
                self._captures.remove(session)

        return cancel

    def watch_extent(
        self, on_extent: Callable[[CanvasExtent], None]
    ) -> Callable[[], None]:
        self._scope.ensure_open()
        subscription = _ExtentSubscription(on_extent=on_extent)
        self._subscriptions.append(subscription)

        def cancel() -> None:
            subscription.live = False

        return cancel

    # -- what a test drives -------------------------------------------------

    def draw(self, geometry: Geometry) -> None:
        """Finish the oldest open capture session with ``geometry``, as a user would.

        The geometry's type has to be the shape the session asked for: a polygon
        session finished with a point would be the fake disagreeing with itself.
        """
        self._scope.ensure_open()
        session = next(
            (
                open_session
                for open_session in self._captures
                if not open_session.done
                and open_session.shape == geometry.geometry_type
            ),
            None,
        )
        if session is None:
            open_shapes = [open_session.shape for open_session in self._captures]
            raise QgisSdkUnsupportedCapabilityError(
                f"no {geometry.geometry_type} capture session is open; open "
                f"sessions are {open_shapes}"
            )
        session.done = True
        self._drawn.append(geometry)
        self._captures.remove(session)
        session.on_capture(geometry)

    def select(self, layer_id: str, extent: CanvasExtent) -> None:
        """Declare what is selected in one layer, and where that is."""
        self._scope.ensure_open()
        self._selections[layer_id] = extent

    def declare_theme(self, name: str) -> None:
        """Add one map theme to the project this canvas draws from.

        A theme is project configuration rather than a canvas operation - the
        canvas only ever picks one - so the contract asks the backend for a
        theme instead of assuming one exists.
        """
        self._scope.ensure_open()
        if name not in self._theme_names:
            self._theme_names.append(name)

    def clear_selection(self, layer_id: str) -> None:
        """Declare that nothing is selected in one layer."""
        self._scope.ensure_open()
        self._selections.pop(layer_id, None)

    def set_extent(self, extent: CanvasExtent) -> None:
        """Move the canvas without a zoom, the way a pan does, and notify."""
        self._scope.ensure_open()
        self._extent = extent
        self._notify(extent)

    def open_captures(self) -> tuple[str, ...]:
        """The shapes of the sessions still open, oldest first."""
        return tuple(session.shape for session in self._captures if not session.done)

    def drawn(self) -> tuple[Geometry, ...]:
        """Every geometry a capture session was finished with, in order."""
        return tuple(self._drawn)

    def subscriptions(self) -> int:
        """How many extent subscriptions are live, for a disposal assertion."""
        return sum(1 for subscription in self._subscriptions if subscription.live)

    # -- internals ----------------------------------------------------------

    def _resolve(self, target: ZoomTarget) -> CanvasExtent:
        if target.kind == "extent":
            assert target.extent is not None  # refused by ZoomTarget itself
            return _margin(target.extent, target.margin)
        layer_id = str(target.layer_id)
        if target.kind == "selection":
            selection = self._selections.get(layer_id)
            if selection is None:
                raise QgisSdkUnsupportedCapabilityError(
                    f"nothing is selected in layer {layer_id!r}, so there is "
                    "nothing to zoom to"
                )
            return _margin(selection, target.margin)
        layer_extent = self._layer_extents.get(layer_id)
        if layer_extent is None:
            raise QgisSdkUnsupportedCapabilityError(
                f"layer {layer_id!r} has no extent this canvas knows of"
            )
        return _margin(layer_extent, target.margin)

    def _notify(self, extent: CanvasExtent) -> None:
        for subscription in list(self._subscriptions):
            if subscription.live:
                subscription.on_extent(extent)


def _margin(extent: CanvasExtent, margin: float) -> CanvasExtent:
    """Grow ``extent`` by ``margin`` of its own span on every side."""
    grow_x = extent.width * margin
    grow_y = extent.height * margin
    return CanvasExtent(
        x_min=extent.x_min - grow_x,
        y_min=extent.y_min - grow_y,
        x_max=extent.x_max + grow_x,
        y_max=extent.y_max + grow_y,
        crs=extent.crs,
    )


def _refuse_unknown_shape(shape: str) -> None:
    """Refuse a shape a tool cannot draw, naming the three it can."""
    if shape not in CAPTURE_SHAPES:
        raise QgisSdkUnsupportedCapabilityError(
            f"{shape!r} is not a capture shape; draw one of {', '.join(CAPTURE_SHAPES)}"
        )
