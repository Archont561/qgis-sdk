"""The dataclasses of print layouts and atlases.

What crosses the service boundary: how a layout is drawn, what an atlas is
configured to do, a finished export, and the requests a job body receives.
The format tables and wire schemas they validate against live in
:mod:`._formats`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ._formats import DEFAULT_ATLAS_PATTERN, check_format

__all__ = [
    "AtlasExport",
    "AtlasInfo",
    "AtlasPage",
    "AtlasRequest",
    "LayoutExport",
    "LayoutInfo",
    "LayoutRequest",
    "LayoutSettings",
]


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
        check_format(self.format)

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
        check_format(self.format)

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
