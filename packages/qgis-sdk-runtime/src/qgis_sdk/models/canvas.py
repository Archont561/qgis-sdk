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

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from qgis_sdk.models.features import GEOMETRY

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

#: What ``zoom_to`` may be aimed at. ``layer`` and ``selection`` name a layer;
#: ``extent`` carries the box, so a page can zoom to what it computed.
ZOOM_KINDS = ("layer", "selection", "extent")

#: The largest margin ``zoom_to`` accepts, as a fraction. Ten times the target
#: is already a map nobody asked for; a larger number is a unit mistake, and it
#: is refused by name rather than drawn.
MAX_ZOOM_MARGIN = 10.0

CaptureShape = Literal["point", "line", "polygon"]
ZoomKind = Literal["layer", "selection", "extent"]


def _is_number(value: Any) -> bool:
    """Whether ``value`` is a real, finite number (``bool`` is not a number)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


@dataclass(frozen=True, slots=True)
class CanvasExtent:
    """A box in the canvas's CRS: four finite numbers, ordered.

    ``x_min == x_max`` is legal - a canvas zoomed onto a single point reports a
    degenerate box, and so does a one-vertex line - but a box whose corners are
    the wrong way round is a bug in the caller, not a box.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    crs: str | None = None

    def __post_init__(self) -> None:
        for name in ("x_min", "y_min", "x_max", "y_max"):
            if not _is_number(getattr(self, name)):
                raise ValueError(f"{name} is a finite number")
        if self.x_min > self.x_max:
            raise ValueError(f"x_min {self.x_min} is greater than x_max {self.x_max}")
        if self.y_min > self.y_max:
            raise ValueError(f"y_min {self.y_min} is greater than y_max {self.y_max}")
        if self.crs is not None and (not isinstance(self.crs, str) or not self.crs):
            raise ValueError("crs is a nonempty string or None")

    @property
    def width(self) -> float:
        """The box's width in CRS units."""
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        """The box's height in CRS units."""
        return self.y_max - self.y_min

    @classmethod
    def from_bounds(
        cls,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        crs: str | None = None,
    ) -> CanvasExtent:
        """Build the box from the order a rectangle is usually written in."""
        return cls(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max, crs=crs)

    def to_wire(self) -> dict[str, Any]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Any) -> CanvasExtent:
        """Read one extent, refusing a field it does not know."""
        if not isinstance(value, Mapping):
            raise TypeError("a CanvasExtent is a mapping")
        known = {"x_min", "y_min", "x_max", "y_max", "crs"}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a CanvasExtent has no field {min(unknown)!r}")
        missing = {"x_min", "y_min", "x_max", "y_max"} - set(value)
        if missing:
            raise ValueError(f"a CanvasExtent needs {min(missing)!r}")
        return cls(
            x_min=value["x_min"],
            y_min=value["y_min"],
            x_max=value["x_max"],
            y_max=value["y_max"],
            crs=value.get("crs"),
        )


@dataclass(frozen=True, slots=True)
class CanvasPoint:
    """The canvas centre: two finite numbers in the canvas's CRS."""

    x: float
    y: float
    crs: str | None = None

    def __post_init__(self) -> None:
        for name in ("x", "y"):
            if not _is_number(getattr(self, name)):
                raise ValueError(f"{name} is a finite number")
        if self.crs is not None and (not isinstance(self.crs, str) or not self.crs):
            raise ValueError("crs is a nonempty string or None")

    def to_wire(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "crs": self.crs}

    @classmethod
    def from_wire(cls, value: Any) -> CanvasPoint:
        if not isinstance(value, Mapping):
            raise TypeError("a CanvasPoint is a mapping")
        unknown = set(value) - {"x", "y", "crs"}
        if unknown:
            raise ValueError(f"a CanvasPoint has no field {min(unknown)!r}")
        if "x" not in value or "y" not in value:
            raise ValueError("a CanvasPoint needs x and y")
        return cls(x=value["x"], y=value["y"], crs=value.get("crs"))


@dataclass(frozen=True, slots=True)
class MapThemes:
    """The project's map themes, and the one the canvas is drawn with.

    ``active`` is ``None`` on a project with no themes, on a canvas drawn
    without one, and never a name that ``names`` does not carry - a page that
    reads the answer and looks the active theme up would otherwise find nothing.
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

    def to_wire(self) -> dict[str, Any]:
        return {"names": list(self.names), "active": self.active}

    @classmethod
    def from_wire(cls, value: Any) -> MapThemes:
        if not isinstance(value, Mapping):
            raise TypeError("MapThemes is a mapping")
        unknown = set(value) - {"names", "active"}
        if unknown:
            raise ValueError(f"MapThemes has no field {min(unknown)!r}")
        return cls(
            names=tuple(value.get("names", ())),
            active=value.get("active"),
        )


@dataclass(frozen=True, slots=True)
class ZoomTarget:
    """What ``zoom_to`` is aimed at: a layer, its selection, or a box.

    One model rather than three methods, because the three share an answer (the
    extent the canvas landed on) and a caller picks one with :meth:`layer`,
    :meth:`selection` or :meth:`to_extent` rather than by naming a kind string.
    """

    kind: ZoomKind
    layer_id: str | None = None
    extent: CanvasExtent | None = None
    #: How much of the target's surroundings to include, as a fraction of its
    #: size: ``0.1`` leaves a tenth of the target's span on every side.
    margin: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ZOOM_KINDS:
            raise ValueError(f"kind is one of {', '.join(ZOOM_KINDS)}")
        if not _is_number(self.margin) or not 0.0 <= self.margin <= MAX_ZOOM_MARGIN:
            raise ValueError(f"margin is between 0 and {MAX_ZOOM_MARGIN}")
        if self.kind == "extent":
            if self.extent is None:
                raise ValueError("zooming to an extent needs the extent")
            if self.layer_id is not None:
                raise ValueError("zooming to an extent names no layer")
        else:
            if not isinstance(self.layer_id, str) or not self.layer_id:
                raise ValueError(f"zooming to a {self.kind} needs a layer id")
            if self.extent is not None:
                raise ValueError(f"zooming to a {self.kind} carries no extent")

    @classmethod
    def layer(cls, layer_id: str, *, margin: float = 0.0) -> ZoomTarget:
        """Zoom to one layer's extent."""
        return cls(kind="layer", layer_id=layer_id, margin=margin)

    @classmethod
    def selection(cls, layer_id: str, *, margin: float = 0.0) -> ZoomTarget:
        """Zoom to the features selected in one layer."""
        return cls(kind="selection", layer_id=layer_id, margin=margin)

    @classmethod
    def to_extent(cls, extent: CanvasExtent, *, margin: float = 0.0) -> ZoomTarget:
        """Zoom to a box the caller computed."""
        return cls(kind="extent", extent=extent, margin=margin)

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "layer_id": self.layer_id,
            "extent": None if self.extent is None else self.extent.to_wire(),
            "margin": self.margin,
        }

    @classmethod
    def from_wire(cls, value: Any) -> ZoomTarget:
        if not isinstance(value, Mapping):
            raise TypeError("a ZoomTarget is a mapping")
        unknown = set(value) - {"kind", "layer_id", "extent", "margin"}
        if unknown:
            raise ValueError(f"a ZoomTarget has no field {min(unknown)!r}")
        if "kind" not in value:
            raise ValueError("a ZoomTarget needs a kind")
        raw_extent = value.get("extent")
        return cls(
            kind=value["kind"],
            layer_id=value.get("layer_id"),
            extent=None if raw_extent is None else CanvasExtent.from_wire(raw_extent),
            margin=value.get("margin", 0.0),
        )


# ---------------------------------------------------------------------------
# The wire shapes the generated TypeScript types come from
# ---------------------------------------------------------------------------

CANVAS_EXTENT: dict[str, Any] = {
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

CANVAS_POINT: dict[str, Any] = {
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

MAP_THEMES: dict[str, Any] = {
    "type": "object",
    "title": "MapThemes",
    "properties": {
        "names": {"type": "array", "items": {"type": "string"}},
        "active": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["names"],
    "additionalProperties": False,
}

ZOOM_REQUEST: dict[str, Any] = {
    "type": "object",
    "title": "ZoomRequest",
    "properties": {
        "kind": {"enum": list(ZOOM_KINDS)},
        "layer_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "extent": {"anyOf": [CANVAS_EXTENT, {"type": "null"}]},
        "margin": {"type": "number"},
    },
    "required": ["kind"],
    "additionalProperties": False,
}

CAPTURE_REQUEST: dict[str, Any] = {
    "type": "object",
    "title": "CaptureRequest",
    "properties": {"shape": {"enum": list(CAPTURE_SHAPES)}},
    "required": ["shape"],
    "additionalProperties": False,
}

#: The one event a capture stream carries: the geometry the user drew. Sharing
#: the feature geometry schema is the point - a captured polygon is the same
#: value a page reads from a feature.
CAPTURE_GEOMETRY: dict[str, Any] = GEOMETRY
