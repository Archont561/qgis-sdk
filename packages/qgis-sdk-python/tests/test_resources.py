"""The packaged style catalog is reviewed data, and its resources ship with it."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest
from qgis_sdk.models import (
    QgisSdkPackagedResourceError,
    QgisSdkStyleNotFoundError,
    StyleSpec,
    VectorLayerInfo,
)
from qgis_sdk.resources import STYLE_CATALOG, STYLE_DIRECTORY, require_style, style_path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "qgis_sdk"


def layer(**overrides: object) -> VectorLayerInfo:
    values: dict[str, object] = {
        "id": "layer-1",
        "name": "points",
        "geometry_type": "point",
        "field_names": ("id", "value"),
        "crs": "EPSG:4326",
    }
    values.update(overrides)
    return VectorLayerInfo(**values)  # type: ignore[arg-type]


def test_catalog_is_not_empty_and_keys_match_the_specifications() -> None:
    assert STYLE_CATALOG, "the SDK must ship at least one reviewed style"

    for identifier, spec in STYLE_CATALOG.items():
        assert spec.id == identifier


@pytest.mark.parametrize("identifier", sorted(STYLE_CATALOG))
def test_every_catalog_entry_ships_its_resource_inside_the_package(
    identifier: str,
) -> None:
    path = style_path(identifier)

    assert path.is_file()
    assert path.parent == STYLE_DIRECTORY
    # Resolved from the package, never from an ambient or caller-supplied path.
    assert PACKAGE_ROOT in path.resolve().parents


@pytest.mark.parametrize("identifier", sorted(STYLE_CATALOG))
def test_every_packaged_qml_parses_and_has_no_external_reference(
    identifier: str,
) -> None:
    root = ElementTree.parse(style_path(identifier)).getroot()

    assert root.tag == "qgis"
    renderer = root.find("renderer-v2")
    assert renderer is not None, "a packaged style must define a renderer"
    # Symbols only: a style that carried a source dependency could not be applied
    # from the package alone.
    assert renderer.get("type") is not None


def test_unknown_identifier_is_refused_with_a_structured_error() -> None:
    with pytest.raises(QgisSdkStyleNotFoundError) as error:
        style_path("reference/not-a-style")

    assert error.value.style == "reference/not-a-style"


def test_a_catalog_entry_without_its_file_is_reported_as_a_packaging_defect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Nothing ships a broken package on purpose, so this drives the defect path
    # directly: the catalog still names the style, but no file is there.
    from qgis_sdk import resources

    monkeypatch.setattr(resources, "STYLE_DIRECTORY", tmp_path)

    with pytest.raises(QgisSdkPackagedResourceError) as error:
        resources.style_path("reference/point-output")

    assert error.value.style == "reference/point-output"
    assert error.value.code == "packaged_resource_unavailable"
    assert "is not packaged" in str(error.value)


def test_require_style_returns_the_reviewed_specification() -> None:
    spec = require_style("reference/point-output")

    assert spec.geometry_type == "point"
    assert spec.required_fields == ("id", "value")


def test_a_matching_layer_has_no_incompatibility() -> None:
    spec = StyleSpec(
        id="reference/point-output",
        resource="reference-point-output.qml",
        geometry_type="point",
        required_fields=("id", "value"),
    )

    assert spec.incompatibilities(layer()) == ()


def test_geometry_mismatch_names_both_geometries() -> None:
    spec = StyleSpec(
        id="reference/line-output",
        resource="reference-line-output.qml",
        geometry_type="line",
        required_fields=(),
    )

    reasons = spec.incompatibilities(layer())

    assert len(reasons) == 1
    assert "line" in reasons[0]
    assert "point" in reasons[0]


def test_missing_fields_are_listed_together() -> None:
    spec = StyleSpec(
        id="reference/point-output",
        resource="reference-point-output.qml",
        geometry_type="point",
        required_fields=("id", "value"),
    )

    reasons = spec.incompatibilities(layer(field_names=()))

    assert len(reasons) == 1
    assert "id" in reasons[0]
    assert "value" in reasons[0]


def test_geometry_and_field_mismatches_are_both_reported() -> None:
    spec = StyleSpec(
        id="reference/point-output",
        resource="reference-point-output.qml",
        geometry_type="point",
        required_fields=("value",),
    )

    reasons = spec.incompatibilities(layer(geometry_type="line", field_names=("id",)))

    assert len(reasons) == 2
