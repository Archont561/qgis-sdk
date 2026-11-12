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

from ._canvas import NativeCanvas
from ._tool import CaptureTool as _CaptureTool  # noqa: F401

__all__ = ["NativeCanvas"]
