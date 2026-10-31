"""Real PyQGIS features: the three encodings, and a commit that reaches disk.

Opt-in under ``QGIS_SDK_NATIVE_SERVICES=1``. The shared contract suite proves
the fake and the adapter answer the same page shapes; these tests prove the
parts only QGIS can answer - that WKB, WKT and GeoJSON describe one geometry
that agrees with itself, and that an edit committed through a session is in the
file a second reader opens.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import FeatureQuery

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services


def _features(services: Services):
    assert services.features is not None
    return services.features


def _only(page):
    """The single feature a page holds, so the row meant is named, not assumed."""
    assert len(page.items) == 1, [feature.id for feature in page.items]
    return page.items[0]


def test_the_three_encodings_describe_the_same_point(native_services: Services) -> None:
    features = _features(native_services)
    assert native_services.fixture_layer is not None
    layer_id = native_services.fixture_layer()

    wkb = features.feature(layer_id, 1, encoding="wkb")
    wkt = features.feature(layer_id, 1, encoding="wkt")
    geojson = features.feature(layer_id, 1, encoding="geojson")

    assert wkb.geometry is not None and wkt.geometry is not None
    assert geojson.geometry is not None
    for geometry in (wkb.geometry, wkt.geometry, geojson.geometry):
        assert geometry.geometry_type == "point"
        assert geometry.is_empty is False
        assert geometry.crs == conftest.FIXTURE_CRS
    # WKB is base64 of real bytes; the other two are text a renderer can read.
    assert base64.b64decode(wkb.geometry.value, validate=True)
    assert "Point" in wkt.geometry.value or "POINT" in wkt.geometry.value
    assert geojson.geometry.value.strip().startswith("{")


def test_a_page_of_wkb_round_trips_through_the_provider(
    native_services: Services,
) -> None:
    features = _features(native_services)
    assert native_services.fixture_layer is not None
    layer_id = native_services.fixture_layer()

    page = features.page(layer_id, FeatureQuery(limit=10, encoding="wkb"))
    again = features.page(layer_id, FeatureQuery(limit=10, encoding="wkb"))

    assert page.to_wire() == again.to_wire()
    assert [feature.id for feature in page.items] == [1, 2, 3]


def test_a_committed_edit_is_in_the_file_a_second_reader_opens(
    native_services: Services,
) -> None:
    assert native_services.editable_layer is not None
    layer_id = native_services.editable_layer()
    features = _features(native_services)

    session = features.begin_edit(layer_id)
    try:
        added = session.add({"id": 42, "value": "committed"})
        outcome = session.commit()
    finally:
        session.close()

    assert outcome.committed is True
    assert outcome.applied == 1
    # QGIS renumbers a pending add from the provider when the buffer commits, so
    # the id `add` returned is not the stored one; the returned ids are the ones
    # the buffer held (doc-12).
    assert added in outcome.feature_ids
    stored = _only(
        features.page(
            layer_id,
            FeatureQuery(
                limit=10, encoding="wkt", expression="\"value\" = 'committed'"
            ),
        )
    )

    # A fresh reader over the same file sees the row: the commit reached the
    # provider rather than only the layer's buffer.
    from qgis.core import QgsVectorLayer

    path = native_services.editable_dataset
    assert path is not None
    reader = QgsVectorLayer(str(path), "reopened", "ogr")
    assert reader.isValid(), path
    assert reader.featureCount() == 4
    assert reader.getFeature(stored.id).attribute("value") == "committed"
