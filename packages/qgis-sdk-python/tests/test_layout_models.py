"""The layout value types: what crosses a boundary, and what refuses to.

TASK-89. These shapes are the only thing a caller, a worker and a page share, so
each is checked twice: the validation it promises on construction, and that
``to_wire``/``from_wire`` is a round trip. A model that lost a field on the way
to the wire would still compare equal to itself, which is why the wire shape is
asserted literally rather than by round trip alone.
"""

from __future__ import annotations

import pytest
from qgis_sdk.models import (
    ATLAS_EXPORT,
    ATLAS_INFO,
    LAYOUT_EXPORT,
    LAYOUT_FORMATS,
    LAYOUT_INFO,
    SINGLE_PAGE_FORMATS,
    AtlasExport,
    AtlasInfo,
    AtlasPage,
    AtlasRequest,
    LayoutExport,
    LayoutInfo,
    LayoutRequest,
    LayoutSettings,
)
from qgis_sdk.models.layouts import (
    ATLAS_TOKENS,
    DEFAULT_ATLAS_PATTERN,
    LAYOUT_SUFFIXES,
)

# -- the format tables -------------------------------------------------------


def test_the_formats_are_the_suffixes_the_exporter_writes() -> None:
    assert LAYOUT_FORMATS == {"pdf": ".pdf", "png": ".png", "svg": ".svg"}
    assert LAYOUT_SUFFIXES == {".pdf": "pdf", ".png": "png", ".svg": "svg"}
    assert SINGLE_PAGE_FORMATS == frozenset({"png", "svg"})


def test_the_default_atlas_pattern_names_the_page_and_nothing_else() -> None:
    assert DEFAULT_ATLAS_PATTERN == "page-{index:03d}"
    assert ATLAS_TOKENS == ("index", "feature_id")
    assert DEFAULT_ATLAS_PATTERN.format(index=7) == "page-007"


# -- settings ----------------------------------------------------------------


def test_settings_carry_a_resolution_and_the_two_switches() -> None:
    settings = LayoutSettings()

    assert settings.dpi == 300
    assert settings.rasterize is False
    assert settings.georeference is False
    assert settings.to_wire() == {
        "dpi": 300,
        "rasterize": False,
        "georeference": False,
    }


def test_settings_round_trip_through_the_wire() -> None:
    settings = LayoutSettings(dpi=600, rasterize=True, georeference=True)

    assert LayoutSettings.from_wire(settings.to_wire()) == settings


def test_an_absent_settings_object_is_the_default() -> None:
    assert LayoutSettings.from_wire(None) == LayoutSettings()


@pytest.mark.parametrize("dpi", [0, -1, 72.5, True])
def test_a_resolution_that_is_not_a_whole_number_is_refused(dpi: object) -> None:
    with pytest.raises(ValueError, match="dots per inch"):
        LayoutSettings(dpi=dpi)  # type: ignore[arg-type]


# -- a layout ----------------------------------------------------------------


def test_a_layout_is_described_by_its_name_its_pages_and_its_atlas() -> None:
    info = LayoutInfo(id="report", name="report", page_count=2)

    assert info.atlas is None
    assert info.to_wire() == {
        "id": "report",
        "name": "report",
        "page_count": 2,
        "atlas": None,
    }


def test_an_atlas_says_what_it_covers() -> None:
    atlas = AtlasInfo(
        enabled=True,
        coverage_layer="points",
        filename_expression="'sheet-' || @atlas_featureid",
    )
    info = LayoutInfo(id="atlas", name="atlas", page_count=1, atlas=atlas)

    assert info.to_wire()["atlas"] == {
        "enabled": True,
        "coverage_layer": "points",
        "filename_expression": "'sheet-' || @atlas_featureid",
    }
    assert LayoutInfo.from_wire(info.to_wire()) == info


def test_a_layout_with_no_page_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one page"):
        LayoutInfo(id="empty", name="empty", page_count=0)


def test_a_layout_without_a_name_is_refused() -> None:
    with pytest.raises(ValueError, match="nonempty string"):
        LayoutInfo(id="report", name="", page_count=1)


# -- a finished export -------------------------------------------------------


def test_an_export_reports_the_file_and_how_much_of_it() -> None:
    export = LayoutExport(path="/tmp/report.pdf", format="pdf", pages=2, bytes=42)

    assert export.to_wire() == {
        "path": "/tmp/report.pdf",
        "format": "pdf",
        "pages": 2,
        "bytes": 42,
    }
    assert LayoutExport.from_wire(export.to_wire()) == export


@pytest.mark.parametrize(
    ("value", "name"),
    [("tiff", "tiff"), (".pdf", ".pdf")],
)
def test_a_format_the_sdk_does_not_write_is_refused(value: str, name: str) -> None:
    """A suffix is not a format: ``pdf`` writes ``.pdf``, and the export adds it."""
    with pytest.raises(ValueError, match=name):
        LayoutExport(path="/tmp/file", format=value, pages=1, bytes=0)


def test_an_atlas_page_counts_from_one_and_names_its_feature() -> None:
    page = AtlasPage(index=1, feature_id=7, path="/tmp/atlas/page-001.pdf")

    assert page.to_wire() == {
        "index": 1,
        "feature_id": 7,
        "path": "/tmp/atlas/page-001.pdf",
    }
    assert AtlasPage.from_wire(page.to_wire()) == page


def test_an_atlas_page_outside_a_coverage_layer_names_no_feature() -> None:
    page = AtlasPage(index=1, feature_id=None, path="/tmp/atlas/page-001.pdf")

    assert AtlasPage.from_wire(page.to_wire()).feature_id is None


def test_a_page_number_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="counts from one"):
        AtlasPage(index=0, feature_id=1, path="/tmp/page.pdf")


def test_an_atlas_export_lists_its_files_in_the_order_it_wrote_them() -> None:
    run = AtlasExport(
        directory="/tmp/atlas",
        format="pdf",
        pages=(
            AtlasPage(index=1, feature_id=1, path="/tmp/atlas/a.pdf"),
            AtlasPage(index=2, feature_id=3, path="/tmp/atlas/b.pdf"),
        ),
    )

    assert run.paths == ("/tmp/atlas/a.pdf", "/tmp/atlas/b.pdf")
    assert AtlasExport.from_wire(run.to_wire()) == run


# -- what a request carries --------------------------------------------------


def test_a_request_is_plain_values_a_worker_can_hold() -> None:
    request = LayoutRequest(layout="report", format="pdf", destination="/tmp/a.pdf")

    assert request.settings == LayoutSettings()
    assert request.overwrite is False


def test_an_atlas_request_defaults_to_the_shipped_pattern() -> None:
    request = AtlasRequest(layout="atlas", format="png", directory="/tmp/atlas")

    assert request.pattern == DEFAULT_ATLAS_PATTERN
    assert request.overwrite is False


# -- the declared schemas ----------------------------------------------------


def test_the_declared_schemas_name_the_types_the_generator_emits() -> None:
    assert LAYOUT_INFO["title"] == "LayoutInfo"
    assert ATLAS_INFO["title"] == "AtlasInfo"
    assert LAYOUT_EXPORT["title"] == "LayoutExport"
    assert ATLAS_EXPORT["title"] == "AtlasExport"
    assert LAYOUT_INFO["required"] == ["id", "name", "page_count", "atlas"]
    assert LAYOUT_EXPORT["properties"]["format"]["enum"] == sorted(LAYOUT_FORMATS)
