"""Features, their queries, and the pages a query returns."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ._geometry import GEOMETRY_ENCODINGS, Geometry, GeometryEncoding, is_int

__all__ = [
    "DEFAULT_FEATURE_PAGE",
    "MAX_FEATURE_PAGE",
    "Feature",
    "FeaturePage",
    "FeatureQuery",
]

#: The most features one page returns. A larger ask is refused rather than
#: clamped, so a caller never mistakes a short page for the end of the layer.
MAX_FEATURE_PAGE = 1000

#: The page size a query asks for when it names none.
DEFAULT_FEATURE_PAGE = 100


@dataclass(frozen=True, slots=True)
class Feature:
    """One row: the provider's id, its attributes and its geometry or ``None``.

    Attributes are plain JSON values keyed by field name; a field the provider
    has no value for is ``None`` rather than absent, so a page can tell a null
    from a column it never asked for.
    """

    id: int
    attributes: Mapping[str, Any] = field(default_factory=dict)
    geometry: Geometry | None = None

    def __post_init__(self) -> None:
        if not is_int(self.id):
            raise ValueError("a feature id is an integer")

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "attributes": dict(self.attributes),
            "geometry": None if self.geometry is None else self.geometry.to_wire(),
        }

    @classmethod
    def from_wire(cls, value: Any) -> Feature:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a Feature is an object")
        raw_geometry = value.get("geometry")
        return cls(
            id=value.get("id"),
            attributes=dict(value.get("attributes") or {}),
            geometry=None if raw_geometry is None else Geometry.from_wire(raw_geometry),
        )


@dataclass(frozen=True, slots=True)
class FeatureQuery:
    """What a caller may ask of a layer's features, with the bounds applied.

    ``expression`` is server-side: the provider evaluates it and returns only
    the matching rows, so a page never holds the layer to filter it itself.
    ``ids`` and ``bbox`` are the two filters a page can express without writing
    an expression at all. ``limit`` is bounded by ``MAX_FEATURE_PAGE``.
    """

    limit: int = DEFAULT_FEATURE_PAGE
    cursor: str | None = None
    expression: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    ids: tuple[int, ...] | None = None
    encoding: GeometryEncoding = "wkb"
    with_geometry: bool = True

    def __post_init__(self) -> None:
        if not is_int(self.limit) or self.limit < 1:
            raise ValueError("limit is a positive integer")
        if self.limit > MAX_FEATURE_PAGE:
            raise ValueError(
                f"limit is at most {MAX_FEATURE_PAGE} features, not {self.limit}"
            )
        if self.cursor is not None and not str(self.cursor).isdigit():
            raise ValueError("a cursor is the digit string of a feature id")
        if self.encoding not in GEOMETRY_ENCODINGS:
            raise ValueError(
                f"a geometry encoding is one of {GEOMETRY_ENCODINGS}, not {self.encoding!r}"
            )
        if self.bbox is not None and len(self.bbox) != 4:
            raise ValueError("a bbox is (min_x, min_y, max_x, max_y)")
        if self.ids is not None and not all(is_int(item) for item in self.ids):
            raise ValueError("ids are integers")

    @property
    def start(self) -> int | None:
        """The id the page starts after, or ``None`` for the first page."""
        return None if self.cursor is None else int(self.cursor)


@dataclass(frozen=True, slots=True)
class FeaturePage:
    """One bounded page of features, with the cursor for the next one.

    ``next_cursor`` is present only when something is left, and it is the id the
    next page starts *after*, so a client that stops early has lost nothing it
    cannot ask for again.
    """

    items: tuple[Feature, ...] = ()
    truncated: bool = False
    next_cursor: str | None = None
    total: int | None = None

    def __post_init__(self) -> None:
        if self.truncated and self.next_cursor is None:
            raise ValueError("a truncated page carries the cursor of the next one")
        if not self.truncated and self.next_cursor is not None:
            raise ValueError("a page with nothing left carries no cursor")

    def to_wire(self) -> dict[str, Any]:
        page: dict[str, Any] = {
            "items": [feature.to_wire() for feature in self.items],
            "truncated": self.truncated,
        }
        if self.next_cursor is not None:
            page["next_cursor"] = self.next_cursor
        if self.total is not None:
            page["total"] = self.total
        return page
