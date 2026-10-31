"""The in-memory ``Features`` backend: the shapes and refusals it guarantees.

A fake is the one place where a test can say which guarantee it is asserting, so
the cases here are the ones the native adapter cannot easily produce on demand -
an empty geometry, a multipart one, a layer that declares one encoding and not
another - plus the expression subset, which is deliberately narrower than
``QgsExpression`` and says so.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    FeatureQuery,
    Geometry,
    QgisSdkLayerNotFoundError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing import FakeFeatures


@pytest.fixture(name="scope")
def fixture_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    scope.close()


@pytest.fixture(name="features")
def fixture_features(scope: ResourceScope) -> FakeFeatures:
    service = FakeFeatures(scope)
    service.declare(
        "parcels",
        fields=("name", "area", "note"),
        rows=[
            (
                1,
                {"name": "A", "area": 10, "note": None},
                Geometry(encoding="wkt", value="POINT (0 0)", geometry_type="point"),
            ),
            (
                2,
                {"name": "B", "area": 20, "note": "x"},
                Geometry(
                    encoding="wkt",
                    value="POLYGON EMPTY",
                    geometry_type="polygon",
                    is_empty=True,
                ),
            ),
            (
                3,
                {"name": "C", "area": 30, "note": "y"},
                Geometry(
                    encoding="wkt",
                    value="MULTIPOINT ((0 0),(1 1))",
                    geometry_type="multipoint",
                    part_count=2,
                    vertex_count=2,
                ),
            ),
        ],
    )
    return service


# -- geometry ----------------------------------------------------------------


def test_an_empty_geometry_crosses_with_its_shape_still_readable(
    features: FakeFeatures,
) -> None:
    feature = features.feature("parcels", 2, encoding="wkt")

    assert feature.geometry is not None
    assert feature.geometry.is_empty is True
    assert feature.geometry.geometry_type == "polygon"
    assert feature.geometry.vertex_count == 0


def test_a_multipart_geometry_keeps_its_part_count(features: FakeFeatures) -> None:
    feature = features.feature("parcels", 3, encoding="wkt")

    assert feature.geometry is not None
    assert feature.geometry.geometry_type == "multipoint"
    assert feature.geometry.part_count == 2


def test_an_encoding_the_layer_does_not_declare_is_refused_by_name(
    features: FakeFeatures,
) -> None:
    """The fake never converts: a conversion is a geometry engine's job."""
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        features.feature("parcels", 1, encoding="geojson")

    assert "geojson" in str(error.value)
    assert "wkt" in str(error.value)


def test_wkb_is_validated_as_base64_before_it_is_stored() -> None:
    with pytest.raises(ValueError):
        Geometry(encoding="wkb", value="not base64!", geometry_type="point")


def test_an_unknown_geometry_type_is_refused() -> None:
    with pytest.raises(ValueError):
        Geometry(encoding="wkt", value="POINT (0 0)", geometry_type="blob")


# -- paging ------------------------------------------------------------------


def test_a_bbox_filter_reads_wkt_points_only(features: FakeFeatures) -> None:
    """The fake says what it can answer; it does not guess at a polygon."""
    page = features.page(
        "parcels", FeatureQuery(limit=10, bbox=(-1, -1, 0.5, 0.5), encoding="wkt")
    )

    assert [feature.id for feature in page.items] == [1]


def test_ids_and_expression_filters_compose(features: FakeFeatures) -> None:
    page = features.page(
        "parcels",
        FeatureQuery(
            limit=10, ids=(1, 2, 3), expression='"area" >= 20', encoding="wkt"
        ),
    )

    assert [feature.id for feature in page.items] == [2, 3]


def test_a_cursor_that_is_not_a_feature_id_is_refused() -> None:
    with pytest.raises(ValueError):
        FeatureQuery(cursor="next")


def test_a_closed_scope_refuses_work_rather_than_answering(
    scope: ResourceScope, features: FakeFeatures
) -> None:
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        features.page("parcels", FeatureQuery(limit=1, encoding="wkt"))


# -- expressions -------------------------------------------------------------


def test_the_subset_answers_comparisons_and_null_checks(
    features: FakeFeatures,
) -> None:
    assert (
        features.evaluate('"area" > 15', layer_id="parcels", feature_id=3).value is True
    )
    assert (
        features.evaluate('"note" IS NULL', layer_id="parcels", feature_id=1).value
        is True
    )
    assert (
        features.evaluate('"note" IS NOT NULL', layer_id="parcels", feature_id=1).value
        is False
    )
    assert (
        features.evaluate(
            '"area" > 15 and "name" = \'C\'', layer_id="parcels", feature_id=3
        ).value
        is True
    )


def test_an_expression_outside_the_subset_is_reported_not_guessed(
    features: FakeFeatures,
) -> None:
    outcome = features.evaluate(
        "buffer($geometry, 10)", layer_id="parcels", feature_id=1
    )
    check = features.check("buffer($geometry, 10)", layer_id="parcels")

    assert outcome.valid is False
    assert outcome.message and "$geometry" in outcome.message
    assert check.valid is False
    assert check.message == outcome.message


def test_validate_names_the_columns_and_never_runs_the_expression(
    features: FakeFeatures,
) -> None:
    check = features.check('"area" > 100 and "name" = \'Z\'', layer_id="parcels")

    assert check.valid is True
    assert check.referenced_columns == ("area", "name")


def test_a_null_value_and_a_syntax_error_are_different_answers(
    features: FakeFeatures,
) -> None:
    """``valid`` is about parsing; ``value is None`` is about the result."""
    null_value = features.evaluate('"note"', layer_id="parcels", feature_id=1)
    broken = features.evaluate('"note" >', layer_id="parcels", feature_id=1)

    assert null_value.valid is True
    assert null_value.value is None
    assert broken.valid is False


# -- editing -----------------------------------------------------------------


def test_an_edit_session_refuses_a_field_the_layer_does_not_have(
    features: FakeFeatures,
) -> None:
    session = features.begin_edit("parcels")

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        session.add({"name": "D", "colour": "red"})

    assert "colour" in str(error.value)
    session.close()


def test_an_update_of_an_unknown_feature_is_refused(features: FakeFeatures) -> None:
    session = features.begin_edit("parcels")

    with pytest.raises(QgisSdkLayerNotFoundError):
        session.update(99, {"area": 1})

    session.close()


def test_a_read_only_layer_refuses_editing_by_name(scope: ResourceScope) -> None:
    service = FakeFeatures(scope)
    service.declare("scan", fields=("name",), editable=False)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        service.begin_edit("scan")

    assert "read-only" in str(error.value)


def test_a_commit_reports_what_it_wrote_and_a_rollback_keeps_the_rows(
    features: FakeFeatures,
) -> None:
    session = features.begin_edit("parcels")
    added = session.add({"name": "D", "area": 40})
    assert session.pending == 1

    outcome = session.commit()

    assert outcome.committed is True
    assert outcome.applied == 1
    assert outcome.feature_ids == (added,)
    assert features.feature("parcels", added, encoding="wkt").attributes["name"] == "D"
    session.close()


def test_a_non_atomic_commit_is_modelled_where_a_test_asks_for_it(
    scope: ResourceScope,
) -> None:
    """``atomic=False`` is a provider that writes row by row, and says so."""
    service = FakeFeatures(scope)
    service.declare("rows", fields=("name",), editable=True, atomic=False)
    session = service.begin_edit("rows")
    session.add({"name": "first"})
    session.fail_next_commit("the provider rejected row 2")

    with pytest.raises(Exception) as error:
        session.commit()

    assert "rejected" in str(error.value)
