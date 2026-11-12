"""One geometry, encoded, with just enough shape for a page to reason about."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

__all__ = ["GEOMETRY_ENCODINGS", "GEOMETRY_TYPES", "Geometry", "GeometryEncoding"]

#: The encodings a geometry may cross in. ``wkb`` carries standard base64 of the
#: WKB a provider produced; ``wkt`` and ``geojson`` carry text.
GEOMETRY_ENCODINGS = ("wkb", "wkt", "geojson")

#: The geometry vocabulary, lower-case so it reads the same in Python, on the
#: wire and in an expression's ``geometry_type()``.
GEOMETRY_TYPES = (
    "point",
    "line",
    "polygon",
    "multipoint",
    "multiline",
    "multipolygon",
    "geometrycollection",
    "none",
)

GeometryEncoding = Literal["wkb", "wkt", "geojson"]


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class Geometry:
    """One geometry, encoded, with just enough shape for a page to reason about.

    ``part_count`` and ``vertex_count`` are what a feature list needs to say
    "multipart, 42 vertices" without decoding the payload; ``is_empty`` is an
    explicit answer, because an empty geometry and a missing one are different
    facts about a row.
    """

    encoding: GeometryEncoding
    value: str
    geometry_type: str = "none"
    crs: str | None = None
    part_count: int = 0
    vertex_count: int = 0
    is_empty: bool = False

    def __post_init__(self) -> None:
        if self.encoding not in GEOMETRY_ENCODINGS:
            raise ValueError(
                f"a geometry encoding is one of {GEOMETRY_ENCODINGS}, not {self.encoding!r}"
            )
        if self.geometry_type not in GEOMETRY_TYPES:
            raise ValueError(
                f"a geometry type is one of {GEOMETRY_TYPES}, not {self.geometry_type!r}"
            )
        if not isinstance(self.value, str):
            raise TypeError("a geometry carries its payload as a string")
        if self.encoding == "wkb":
            try:
                base64.b64decode(self.value, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("a wkb geometry carries standard base64") from error
        for name, count in (
            ("part_count", self.part_count),
            ("vertex_count", self.vertex_count),
        ):
            if not is_int(count) or count < 0:
                raise ValueError(f"{name} is a non-negative integer")
        if self.is_empty and self.vertex_count:
            raise ValueError("an empty geometry has no vertices")

    def to_wire(self) -> dict[str, Any]:
        return {
            "encoding": self.encoding,
            "value": self.value,
            "geometry_type": self.geometry_type,
            "crs": self.crs,
            "part_count": self.part_count,
            "vertex_count": self.vertex_count,
            "is_empty": self.is_empty,
        }

    @classmethod
    def from_wire(cls, value: Any) -> Geometry:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a Geometry is an object")
        known = {
            "encoding",
            "value",
            "geometry_type",
            "crs",
            "part_count",
            "vertex_count",
            "is_empty",
        }
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a Geometry has no field {min(unknown)!r}")
        return cls(
            encoding=value.get("encoding"),
            value=value.get("value"),
            geometry_type=value.get("geometry_type", "none"),
            crs=value.get("crs"),
            part_count=value.get("part_count", 0),
            vertex_count=value.get("vertex_count", 0),
            is_empty=value.get("is_empty", False),
        )
