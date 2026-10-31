"""Features, their geometry and the values an expression returns.

decision-54 point 3 draws this boundary. A page reads *features*, not a
``QgsVectorLayer``: an id the provider assigned, the attribute values that layer
declares, and its geometry in one of three encodings. Nothing here carries a
native handle, a projection object or a path, so the same value is what the fake
layer, the native adapter and the wire all say.

Three choices are deliberate.

*Geometry crosses encoded, never as an object graph.* WKB is base64 in
``value``, WKT and GeoJSON are text. A page that wants to draw can hand GeoJSON
straight to a renderer; a page that wants to store can keep the WKB byte for
byte. The encoder is named in ``encoding`` so a reader never guesses.

*Paging is by the provider's feature id, ascending.* ``next_cursor`` is the last
id of the page, not an offset: a provider that reorders between two calls cannot
make a client skip a row, and the same query over the same data returns the same
pages.

*An expression outcome is a value or a message, never both.* ``valid`` says
whether the text parsed; a parsed expression that evaluated to a null value is
``valid`` with ``value`` null, which is a different answer from a syntax error.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "DEFAULT_FEATURE_PAGE",
    "EDIT_KINDS",
    "EDIT_OUTCOME",
    "EXPRESSION_CHECK",
    "EXPRESSION_OUTCOME",
    "FEATURE",
    "FEATURE_PAGE",
    "FEATURE_QUERY",
    "GEOMETRY",
    "GEOMETRY_ENCODINGS",
    "GEOMETRY_TYPES",
    "MAX_FEATURE_PAGE",
    "EditOutcome",
    "ExpressionCheck",
    "ExpressionOutcome",
    "Feature",
    "FeaturePage",
    "FeatureQuery",
    "Geometry",
]

#: The most features one page returns. A larger ask is refused rather than
#: clamped, so a caller never mistakes a short page for the end of the layer.
MAX_FEATURE_PAGE = 1000

#: The page size a query asks for when it names none.
DEFAULT_FEATURE_PAGE = 100

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

EDIT_KINDS = ("add", "update", "delete")

GeometryEncoding = Literal["wkb", "wkt", "geojson"]


def _is_int(value: Any) -> bool:
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
            if not _is_int(count) or count < 0:
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
        if not _is_int(self.id):
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
        if not _is_int(self.limit) or self.limit < 1:
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
        if self.ids is not None and not all(_is_int(item) for item in self.ids):
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


@dataclass(frozen=True, slots=True)
class ExpressionCheck:
    """The answer to "does this expression parse": a verdict and, if not, why."""

    valid: bool
    message: str | None = None
    referenced_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.valid and self.message is not None:
            raise ValueError("a valid expression carries no message")
        if not self.valid and not self.message:
            raise ValueError("an invalid expression says why")

    def to_wire(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "message": self.message,
            "referenced_columns": list(self.referenced_columns),
        }


@dataclass(frozen=True, slots=True)
class ExpressionOutcome:
    """One evaluated expression: the value, or the reason there is none.

    ``value`` is a plain JSON value; a parsed expression whose result is null
    is a valid outcome with ``value`` ``None``, which a caller distinguishes
    from a failure by ``valid``.
    """

    valid: bool
    value: Any = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.valid and self.message is not None:
            raise ValueError("a valid outcome carries no message")
        if not self.valid and not self.message:
            raise ValueError("an invalid outcome says why")

    def to_wire(self) -> dict[str, Any]:
        return {"valid": self.valid, "value": self.value, "message": self.message}


@dataclass(frozen=True, slots=True)
class EditOutcome:
    """What one edit request did, before or after a commit.

    ``feature_ids`` is what the provider assigned for an add - a caller needs
    them to refer to the rows it just wrote - and empty for an update or a
    delete, which name a row the caller already had.
    """

    applied: int
    feature_ids: tuple[int, ...] = ()
    committed: bool = False

    def to_wire(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "feature_ids": list(self.feature_ids),
            "committed": self.committed,
        }


# ---------------------------------------------------------------------------
# The wire shapes the generated TypeScript types come from
# ---------------------------------------------------------------------------

GEOMETRY: dict[str, Any] = {
    "type": "object",
    "title": "Geometry",
    "properties": {
        "encoding": {"enum": list(GEOMETRY_ENCODINGS)},
        "value": {"type": "string"},
        "geometry_type": {"enum": list(GEOMETRY_TYPES)},
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "part_count": {"type": "integer", "minimum": 0},
        "vertex_count": {"type": "integer", "minimum": 0},
        "is_empty": {"type": "boolean"},
    },
    "required": ["encoding", "value", "geometry_type"],
    "additionalProperties": False,
}

FEATURE: dict[str, Any] = {
    "type": "object",
    "title": "Feature",
    "properties": {
        "id": {"type": "integer"},
        "attributes": {"type": "object", "additionalProperties": True},
        "geometry": {"anyOf": [GEOMETRY, {"type": "null"}]},
    },
    "required": ["id", "attributes"],
    "additionalProperties": False,
}

FEATURE_QUERY: dict[str, Any] = {
    "type": "object",
    "title": "FeatureQuery",
    "properties": {
        "limit": {"type": "integer", "minimum": 1},
        "cursor": {"type": "string", "pattern": "[0-9]+"},
        "expression": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "bbox": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {"type": "number"},
                },
                {"type": "null"},
            ]
        },
        "ids": {
            "anyOf": [
                {"type": "array", "items": {"type": "integer"}},
                {"type": "null"},
            ]
        },
        "encoding": {"enum": list(GEOMETRY_ENCODINGS)},
        "with_geometry": {"type": "boolean"},
    },
    "additionalProperties": False,
}

FEATURE_PAGE: dict[str, Any] = {
    "type": "object",
    "title": "FeaturePage",
    "properties": {
        "items": {"type": "array", "items": FEATURE},
        "truncated": {"type": "boolean"},
        "next_cursor": {"type": "string"},
        "total": {"type": "integer", "minimum": 0},
    },
    "required": ["items", "truncated"],
    "additionalProperties": False,
}

EXPRESSION_OUTCOME: dict[str, Any] = {
    "type": "object",
    "title": "ExpressionOutcome",
    "properties": {
        "valid": {"type": "boolean"},
        "value": {"type": ["string", "number", "boolean", "null", "array", "object"]},
        "message": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["valid", "message"],
    "additionalProperties": False,
}

EDIT_OUTCOME: dict[str, Any] = {
    "type": "object",
    "title": "EditOutcome",
    "properties": {
        "applied": {"type": "integer", "minimum": 0},
        "feature_ids": {"type": "array", "items": {"type": "integer"}},
        "committed": {"type": "boolean"},
    },
    "required": ["applied", "feature_ids", "committed"],
    "additionalProperties": False,
}

EXPRESSION_CHECK: dict[str, Any] = {
    "type": "object",
    "title": "ExpressionCheck",
    "properties": {
        "valid": {"type": "boolean"},
        "message": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "referenced_columns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["valid", "message", "referenced_columns"],
    "additionalProperties": False,
}
