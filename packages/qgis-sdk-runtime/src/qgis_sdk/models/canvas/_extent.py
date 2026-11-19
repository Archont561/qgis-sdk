"""The box a canvas reports: four finite numbers in order, and a CRS."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk._published import REQUIRED, published

from ._checks import is_number as _is_number

__all__ = ["CanvasExtent"]


@dataclass(frozen=True, slots=True)
class CanvasExtent:
    """A box in the canvas's CRS: four finite numbers, ordered.

    ``x_min == x_max`` is legal - a canvas zoomed onto a single point reports a
    degenerate box, and so does a one-vertex line - but a box whose corners are
    the wrong way round is a bug in the caller, not a box.

    Attributes:
        x_min: The west edge, in the canvas CRS.
        y_min: The south edge.
        x_max: The east edge.
        y_max: The north edge.
        crs: The authority code the four numbers are in, if known.
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

    _CC_SPECS_from_bounds_1 = (
        ("cls", REQUIRED, REQUIRED, "positional"),
        ("x_min", float, REQUIRED, "positional"),
        ("y_min", float, REQUIRED, "positional"),
        ("x_max", float, REQUIRED, "positional"),
        ("y_max", float, REQUIRED, "positional"),
        ("crs", str | None, None, "positional"),
    )

    @classmethod
    @published(_CC_SPECS_from_bounds_1, returns=None)
    def from_bounds(_published_values):
        """Build the box from the order a rectangle is usually written in.

        Args:
            x_min: The west edge, in the box's CRS.
            y_min: The south edge.
            x_max: The east edge.
            y_max: The north edge.
            crs: The authority code the four numbers are in, if any.
        """
        return _published_values.cls(
            x_min=_published_values.x_min,
            y_min=_published_values.y_min,
            x_max=_published_values.x_max,
            y_max=_published_values.y_max,
            crs=_published_values.crs,
        )

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
        """Read one extent, refusing a field it does not know.

        Args:
            value: The mapping a page sent.
        """
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
