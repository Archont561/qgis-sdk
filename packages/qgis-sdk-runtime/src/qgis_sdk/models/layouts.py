"""Print layouts and atlases, as a page and a plugin handler see them.

decision-54 point 3 asks for layouts as a curated service: list them, load a
template, export one to a file as a job, and iterate an atlas with progress. The
shapes here are what crosses that boundary, and five choices are deliberate.

*A layout is named by its own name.* ``QgsLayoutManager`` keeps layout names
unique in a project, so the name is already an identifier. A second unique key
would be a second thing to keep in step, and a page would have to carry both to
be useful.

*An export is a file and a format, not a ``QgsLayoutExporter``.* The exporter is
the host's business; what a caller needs is where the bytes went and in which
format, so a finished export is :class:`LayoutExport` and nothing in this module
can render anything.

*PNG and SVG name one image, PDF holds many pages.* ``pages`` is the count of
pages in the file the export produced: a PDF carries every page of the layout, an
image carries exactly one, and an export of a multi-page layout to an image is
refused by the service rather than answered with a file name that quietly means
the first page.

*An atlas page names its feature.* ``feature_id`` is the id of the coverage
feature that page was drawn for - the one thing a caller can join the file back
to its record with.

*Progress and cancellation are the job's.* A render is handed the two
:class:`~qgis_sdk.services.contracts.Progress` and
:class:`~qgis_sdk.services.contracts.Cancellation` seams rather than inventing a
third, so an export reports to the bar its ``@job`` already owns and a cancelled
atlas stops between pages instead of after the last one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ATLAS_EXPORT",
    "ATLAS_INFO",
    "ATLAS_PAGE",
    "ATLAS_TOKENS",
    "DEFAULT_ATLAS_PATTERN",
    "LAYOUT_EXPORT",
    "LAYOUT_FORMATS",
    "LAYOUT_INFO",
    "LAYOUT_SUFFIXES",
    "SINGLE_PAGE_FORMATS",
    "AtlasExport",
    "AtlasInfo",
    "AtlasPage",
    "AtlasRequest",
    "LayoutExport",
    "LayoutInfo",
    "LayoutRequest",
    "LayoutSettings",
]

#: Export format name -> the suffix the file gets. The table lives here, not in
#: an adapter, so the fake, the native exporter and the ``layouts.export`` host
#: operation refuse the same format and write the same suffix.
LAYOUT_FORMATS: Mapping[str, str] = {"pdf": ".pdf", "png": ".png", "svg": ".svg"}

#: Destination suffix (lower-case) -> format name, the direction the export
#: policy reads: ``plan_export`` looks a destination's suffix up in a table and
#: answers the driver, which for a layout is the format it was written in.
LAYOUT_SUFFIXES: Mapping[str, str] = {
    suffix: name for name, suffix in LAYOUT_FORMATS.items()
}

#: The formats that hold one page. A PDF holds as many as the layout has.
SINGLE_PAGE_FORMATS = frozenset({"png", "svg"})

#: The default atlas file name pattern. Index only, because a coverage feature's
#: id need not be unique across a project and a pattern naming one is a caller's
#: decision, not the default.
DEFAULT_ATLAS_PATTERN = "page-{index:03d}"

#: The placeholders an atlas pattern may use: ``index`` is zero-based and
#: ``feature_id`` is the coverage feature's own id.
ATLAS_TOKENS = ("index", "feature_id")


def _check_format(format: str) -> str:
    """Return ``format`` if it is one this SDK exports, or refuse it by name."""
    if format not in LAYOUT_FORMATS:
        known = ", ".join(sorted(LAYOUT_FORMATS))
        raise ValueError(f"a layout exports to {known}, not {format!r}")
    return format


@dataclass(frozen=True, slots=True)
class LayoutSettings:
    """How a layout is drawn: resolution and the two rasteriser switches.

    ``dpi`` is the resolution a vector format rasterises at when an item cannot
    be written as vectors; ``rasterize`` asks for the whole page as one image,
    which is what a page whose layers carry unsupported effects needs;
    ``georeference`` writes a world file beside the export so the result can be
    opened as a map rather than a picture.
    """

    dpi: int = 300
    rasterize: bool = False
    georeference: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.dpi, int) or isinstance(self.dpi, bool) or self.dpi < 1:
            raise ValueError("a layout's dpi is a whole number of dots per inch")

    def to_wire(self) -> dict[str, Any]:
        return {
            "dpi": self.dpi,
            "rasterize": self.rasterize,
            "georeference": self.georeference,
        }

    @classmethod
    def from_wire(cls, value: Any) -> LayoutSettings:
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("settings are an object")
        return cls(
            dpi=int(value.get("dpi", 300)),
            rasterize=bool(value.get("rasterize", False)),
            georeference=bool(value.get("georeference", False)),
        )


@dataclass(frozen=True, slots=True)
class AtlasInfo:
    """What an atlas is configured to do, whether or not it is enabled."""

    enabled: bool = False
    coverage_layer: str | None = None
    filename_expression: str | None = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "coverage_layer": self.coverage_layer,
            "filename_expression": self.filename_expression,
        }

    @classmethod
    def from_wire(cls, value: Any) -> AtlasInfo:
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("an atlas is an object or null")
        return cls(
            enabled=bool(value.get("enabled", False)),
            coverage_layer=value.get("coverage_layer"),
            filename_expression=value.get("filename_expression"),
        )


#: The wire shape of one layout. ``atlas`` is present and ``null`` rather than
#: omitted: a page that had to tell "no atlas" from "a field the host forgot"
#: would otherwise guess.
ATLAS_INFO: dict[str, Any] = {
    "type": "object",
    "title": "AtlasInfo",
    "properties": {
        "enabled": {"type": "boolean"},
        "coverage_layer": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "filename_expression": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["enabled", "coverage_layer", "filename_expression"],
    "additionalProperties": False,
}

LAYOUT_INFO: dict[str, Any] = {
    "type": "object",
    "title": "LayoutInfo",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "page_count": {"type": "integer", "minimum": 1},
        "atlas": {"anyOf": [ATLAS_INFO, {"type": "null"}]},
    },
    "required": ["id", "name", "page_count", "atlas"],
    "additionalProperties": False,
}

LAYOUT_EXPORT: dict[str, Any] = {
    "type": "object",
    "title": "LayoutExport",
    "properties": {
        "path": {"type": "string"},
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pages": {"type": "integer", "minimum": 1},
        "bytes": {"type": "integer", "minimum": 0},
    },
    "required": ["path", "format", "pages", "bytes"],
    "additionalProperties": False,
}

ATLAS_PAGE: dict[str, Any] = {
    "type": "object",
    "title": "AtlasPage",
    "properties": {
        "index": {"type": "integer", "minimum": 1},
        "feature_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "path": {"type": "string"},
    },
    "required": ["index", "feature_id", "path"],
    "additionalProperties": False,
}

ATLAS_EXPORT: dict[str, Any] = {
    "type": "object",
    "title": "AtlasExport",
    "properties": {
        "directory": {"type": "string"},
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pages": {"type": "array", "items": ATLAS_PAGE},
    },
    "required": ["directory", "format", "pages"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class LayoutInfo:
    """One print layout in the project: its name, its pages, its atlas."""

    id: str
    name: str
    page_count: int
    atlas: AtlasInfo | None = None

    def __post_init__(self) -> None:
        for field in ("id", "name"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} is a nonempty string")
        if not isinstance(self.page_count, int) or self.page_count < 1:
            raise ValueError("a layout has at least one page")

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "page_count": self.page_count,
            "atlas": None if self.atlas is None else self.atlas.to_wire(),
        }

    @classmethod
    def from_wire(cls, value: Any) -> LayoutInfo:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a layout is an object")
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            page_count=int(value["page_count"]),
            atlas=AtlasInfo.from_wire(value.get("atlas")),
        )


@dataclass(frozen=True, slots=True)
class LayoutExport:
    """A finished export: the file, its format, how many pages, how many bytes."""

    path: str
    format: str
    pages: int
    bytes: int

    def __post_init__(self) -> None:
        _check_format(self.format)

    def to_wire(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "pages": self.pages,
            "bytes": self.bytes,
        }

    @classmethod
    def from_wire(cls, value: Any) -> LayoutExport:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a layout export is an object")
        return cls(
            path=str(value["path"]),
            format=str(value["format"]),
            pages=int(value["pages"]),
            bytes=int(value["bytes"]),
        )


@dataclass(frozen=True, slots=True)
class AtlasPage:
    """One file an atlas wrote, and the coverage feature it was drawn for.

    ``index`` is the page number a user counts from one, which is the number an
    atlas pattern's ``{index}`` fills and the number a page shows; the coverage
    feature itself is an id, so it is spelled ``feature_id`` and is ``None``
    only for a page an atlas drew outside a coverage layer.
    """

    index: int
    feature_id: int | None
    path: str

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("an atlas page index counts from one")

    def to_wire(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "feature_id": self.feature_id,
            "path": self.path,
        }

    @classmethod
    def from_wire(cls, value: Any) -> AtlasPage:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("an atlas page is an object")
        feature_id = value.get("feature_id")
        return cls(
            index=int(value["index"]),
            feature_id=None if feature_id is None else int(feature_id),
            path=str(value["path"]),
        )


@dataclass(frozen=True, slots=True)
class AtlasExport:
    """Every file an atlas run wrote, in coverage order."""

    directory: str
    format: str
    pages: tuple[AtlasPage, ...] = ()

    def __post_init__(self) -> None:
        _check_format(self.format)

    @property
    def paths(self) -> tuple[str, ...]:
        """The files the run wrote, in the order it wrote them."""
        return tuple(page.path for page in self.pages)

    def to_wire(self) -> dict[str, Any]:
        return {
            "directory": self.directory,
            "format": self.format,
            "pages": [page.to_wire() for page in self.pages],
        }

    @classmethod
    def from_wire(cls, value: Any) -> AtlasExport:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("an atlas export is an object")
        return cls(
            directory=str(value["directory"]),
            format=str(value["format"]),
            pages=tuple(AtlasPage.from_wire(page) for page in value["pages"]),
        )


@dataclass(frozen=True, slots=True)
class LayoutRequest:
    """One render, as a job body receives it: plain values, no live layout.

    ``destination`` is a resolved path, because only a minted ref is authority
    and resolving one is a driving-thread act (decision-20). A body therefore
    never sees a ref it could re-resolve, and never sees a ``QgsLayout``.
    """

    layout: str
    format: str
    destination: str
    settings: LayoutSettings = LayoutSettings()
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class AtlasRequest:
    """One atlas run, as a job body receives it."""

    layout: str
    format: str
    directory: str
    pattern: str = DEFAULT_ATLAS_PATTERN
    settings: LayoutSettings = LayoutSettings()
    overwrite: bool = False
