"""The map canvas as a Protocol: see it, move it, theme it, capture from it.

decision-54 point 3 makes the canvas a service of its own. It is the one service
whose subject is not data but *the view the user is looking at*, and that changes
its shape in three ways.

*Reads and changes are different authority.* Looking at an extent is not the same
permission as moving the map under somebody's cursor, so the host grants
``canvas.read`` for the first four methods and ``canvas.control`` for
``zoom_to``, ``refresh`` and ``apply_theme``.

*Nothing here blocks on a user.* A capture session is a drawing that takes as
long as a person takes, so :meth:`Canvas.capture` starts one and calls back when
it finishes; it returns a canceller rather than waiting. The same is true of
:meth:`Canvas.watch_extent`: a page subscribes, and the host tells it when the
map moved - the canvas is the one service with no request/response shape for
events, because the events are not answers to anything.

*There is no canvas on a server.* QGIS Server draws from a map *settings* built
per request, not from a canvas a user pans. The native adapter refuses every
method here by name on that host rather than inventing a canvas-shaped facade
(decision-54 status review).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from qgis_sdk.models.canvas import CanvasExtent, CanvasPoint, MapThemes, ZoomTarget
from qgis_sdk.models.features import Geometry

__all__ = ["Canvas", "CaptureCanceller", "ExtentListener"]

#: Cancels a capture session or an extent subscription; idempotent, because a
#: closing view races the user all the time.
CaptureCanceller = Callable[[], None]
ExtentListener = Callable[[CanvasExtent], None]


class Canvas(Protocol):
    """The map the user is looking at.

    Every method raises ``QgisSdkUnsupportedCapabilityError`` on a host with no
    canvas - a QGIS Server, a standalone application that never opened a map -
    naming the host rather than returning an empty extent a page would draw.
    """

    def extent(self) -> CanvasExtent:
        """The canvas's current extent, in its own CRS."""
        ...

    def scale(self) -> float:
        """The canvas's scale denominator: 1:``scale`` on screen."""
        ...

    def crs(self) -> str | None:
        """The canvas's destination CRS as an auth id, or ``None`` when unset."""
        ...

    def center(self) -> CanvasPoint:
        """The canvas centre, in the canvas's CRS."""
        ...

    def zoom_to(self, target: ZoomTarget) -> CanvasExtent:
        """Move the canvas onto ``target`` and report the extent it landed on.

        A target the canvas cannot honour - a layer with no extent, a layer with
        nothing selected - raises ``QgisSdkUnsupportedCapabilityError`` instead
        of leaving the map where it was and reporting success.
        """
        ...

    def refresh(self) -> None:
        """Redraw the canvas, keeping its extent."""
        ...

    def themes(self) -> MapThemes:
        """The project's map themes and the one the canvas is drawn with."""
        ...

    def apply_theme(self, name: str) -> MapThemes:
        """Draw the canvas with one map theme and report the result.

        An unknown theme raises ``QgisSdkThemeNotFoundError`` carrying the name;
        the canvas keeps whatever theme it had.
        """
        ...

    def capture(
        self, shape: str, on_capture: Callable[[Geometry], None]
    ) -> CaptureCanceller:
        """Start a capture session; ``on_capture`` gets the geometry drawn.

        ``shape`` is one of ``point``, ``line`` or ``polygon``. The session ends
        when the user finishes, and the returned canceller ends it without a
        callback - which is what a page closing, or a second capture starting,
        does. A session cancelled by the caller never calls ``on_capture``.
        """
        ...

    def watch_extent(self, on_extent: ExtentListener) -> CaptureCanceller:
        """Call ``on_extent`` whenever the canvas moves, until cancelled.

        The listener sees every change of extent after the subscription, in the
        order the canvas produced them. The returned canceller stops the
        subscription; it is idempotent.
        """
        ...
