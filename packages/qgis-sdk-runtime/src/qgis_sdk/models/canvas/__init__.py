"""The map canvas, as a page and a plugin handler see it.

decision-54 point 3 draws this boundary. The canvas is *the view the user is
looking at*: an extent, a scale, a CRS, a centre, a set of map themes. Nothing
here carries a ``QgsMapCanvas``, a ``QgsRectangle`` or a ``QgsCoordinateReferenceSystem``,
so the fake and the native adapter answer the same values and a page cannot tell
which one it is talking to.

Four choices are deliberate.

*An extent is numbers and a CRS, not a rectangle object.* Four doubles in the
canvas's own CRS plus the CRS's identifier are what a page needs to draw a box,
place a marker or ask for features inside it; the object that produced them is
the host's business.

*Zooming reports where it landed.* ``zoom_to`` returns the canvas's extent after
the move rather than ``None``: a page that asked for a layer's extent has to
render something, and asking again is a second round trip that can disagree with
the first.

*Themes are names, and the active one is part of the answer.* A theme list with
no active entry leaves a page guessing which style the map is drawn in, so
:class:`MapThemes` refuses an ``active`` name that is not in ``names``.

*Capture is a shape, not a tool object.* A caller asks for a ``point``, ``line``
or ``polygon``; how the host collects it - a map tool, a digitising widget, a
scripted fake - is not part of the contract, and a drawn geometry comes back in
the same :class:`~qgis_sdk.models.features.Geometry` a feature does.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from dataclasses import dataclass as _dataclass
from typing import Any as _Any
from typing import Literal as _Literal

from qgis_sdk.models.features import GEOMETRY as _GEOMETRY

from ._checks import is_number as _is_number
from ._extent import CanvasExtent
from ._zoom import MAX_ZOOM_MARGIN, ZOOM_KINDS, ZoomKind, ZoomTarget

__all__ = [
    "CANVAS_EXTENT",
    "CANVAS_POINT",
    "CAPTURE_REQUEST",
    "CAPTURE_SHAPES",
    "MAP_THEMES",
    "MAX_ZOOM_MARGIN",
    "ZOOM_KINDS",
    "ZOOM_REQUEST",
    "CanvasExtent",
    "CanvasPoint",
    "CaptureShape",
    "MapThemes",
    "ZoomKind",
    "ZoomTarget",
]

#: The shapes a capture session may draw. The vocabulary is the geometry names a
#: page already knows, narrowed to the three a user can draw: a multipoint, a
#: multiline and a collection are what a *provider* stores, not what a tool
#: collects.
CAPTURE_SHAPES = ("point", "line", "polygon")

CaptureShape = _Literal["point", "line", "polygon"]


@_dataclass(frozen=True, slots=True)
class CanvasPoint:
    """The canvas centre: two finite numbers in the canvas's CRS.

    Attributes:
        x: The easting, in the CRS the point names.
        y: The northing.
        crs: The authority code the numbers are in, if any.
    """

    x: float
    y: float
    crs: str | None = None

    def __post_init__(self) -> None:
        for name in ("x", "y"):
            if not _is_number(getattr(self, name)):
                raise ValueError(f"{name} is a finite number")
        if self.crs is not None and (not isinstance(self.crs, str) or not self.crs):
            raise ValueError("crs is a nonempty string or None")

    def to_wire(self) -> dict[str, _Any]:
        return {"x": self.x, "y": self.y, "crs": self.crs}

    @classmethod
    def from_wire(cls, value: _Any) -> CanvasPoint:
        """Read one point, refusing a field it does not know.

        Args:
            value: The mapping a page sent.
        """
        if not isinstance(value, _Mapping):
            raise TypeError("a CanvasPoint is a mapping")
        unknown = set(value) - {"x", "y", "crs"}
        if unknown:
            raise ValueError(f"a CanvasPoint has no field {min(unknown)!r}")
        if "x" not in value or "y" not in value:
            raise ValueError("a CanvasPoint needs x and y")
        return cls(x=value["x"], y=value["y"], crs=value.get("crs"))


@_dataclass(frozen=True, slots=True)
class MapThemes:
    """The project's map themes, and the one the canvas is drawn with.

    ``active`` is ``None`` on a project with no themes, on a canvas drawn
    without one, and never a name that ``names`` does not carry - a page that
    reads the answer and looks the active theme up would otherwise find nothing.

    Attributes:
        names: Every theme the project defines, in its own order.
        active: The theme the canvas is drawn with, or ``None`` for none.
    """

    names: tuple[str, ...] = ()
    active: str | None = None

    def __post_init__(self) -> None:
        cleaned: list[str] = []
        for name in self.names:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("a map theme name is a nonempty string")
            if name in cleaned:
                raise ValueError(f"map theme {name!r} is listed twice")
            cleaned.append(name)
        if self.active is not None and self.active not in cleaned:
            raise ValueError(f"active theme {self.active!r} is not one of the themes")

    def to_wire(self) -> dict[str, _Any]:
        return {"names": list(self.names), "active": self.active}

    @classmethod
    def from_wire(cls, value: _Any) -> MapThemes:
        """Read one theme list, refusing a field it does not know.

        Args:
            value: The mapping a page sent.
        """
        if not isinstance(value, _Mapping):
            raise TypeError("MapThemes is a mapping")
        unknown = set(value) - {"names", "active"}
        if unknown:
            raise ValueError(f"MapThemes has no field {min(unknown)!r}")
        return cls(
            names=tuple(value.get("names", ())),
            active=value.get("active"),
        )


# ---------------------------------------------------------------------------
# The wire shapes the generated TypeScript types come from
# ---------------------------------------------------------------------------

CANVAS_EXTENT: dict[str, _Any] = {
    "type": "object",
    "title": "CanvasExtent",
    "properties": {
        "x_min": {"type": "number"},
        "y_min": {"type": "number"},
        "x_max": {"type": "number"},
        "y_max": {"type": "number"},
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["x_min", "y_min", "x_max", "y_max"],
    "additionalProperties": False,
}

CANVAS_POINT: dict[str, _Any] = {
    "type": "object",
    "title": "CanvasPoint",
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["x", "y"],
    "additionalProperties": False,
}

MAP_THEMES: dict[str, _Any] = {
    "type": "object",
    "title": "MapThemes",
    "properties": {
        "names": {"type": "array", "items": {"type": "string"}},
        "active": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["names"],
    "additionalProperties": False,
}

ZOOM_REQUEST: dict[str, _Any] = {
    "type": "object",
    "title": "ZoomRequest",
    "properties": {
        "kind": {"enum": list(ZOOM_KINDS)},
        "layer_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "extent": {"anyOf": [CANVAS_EXTENT, {"type": "null"}]},
        # The bound is in the schema as well as the model, so a page is refused
        # before the host and both read the same limit.
        "margin": {
            "type": "number",
            "minimum": 0,
            "maximum": MAX_ZOOM_MARGIN,
        },
    },
    "required": ["kind"],
    "additionalProperties": False,
}

CAPTURE_REQUEST: dict[str, _Any] = {
    "type": "object",
    "title": "CaptureRequest",
    "properties": {"shape": {"enum": list(CAPTURE_SHAPES)}},
    "required": ["shape"],
    "additionalProperties": False,
}

#: The one event a capture stream carries: the geometry the user drew. Sharing
#: the feature geometry schema is the point - a captured polygon is the same
#: value a page reads from a feature.
CAPTURE_GEOMETRY: dict[str, _Any] = _GEOMETRY
