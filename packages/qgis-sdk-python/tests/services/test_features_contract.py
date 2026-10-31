"""Contract: features, expressions and editing through the injected service.

Every backend registered in ``conftest.BACKENDS`` runs these tests unchanged, so
"the fake and the native adapter answer the same contract" is a property of the
run rather than a claim. The fixture dataset is the reference GeoJSON three
points the rest of the services suite already uses: ids 1-3, values a-c, and
WGS 84 geometry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import FeatureQuery, QgisSdkLayerNotFoundError

if TYPE_CHECKING:
    Services = conftest.Services
    Features = object


def _features(services: Services):
    assert services.features is not None, "this backend has no features service"
    return services.features


def _layer(services: Services) -> str:
    """The reference-points layer, opened if the backend opens it on demand."""
    assert services.fixture_layer is not None
    return services.fixture_layer()


def _point_ids(page) -> list[int]:
    return [feature.id for feature in page.items]


# -- paging ------------------------------------------------------------------


def test_a_page_is_ordered_by_feature_id_and_says_what_is_left(
    services: Services,
) -> None:
    page = _features(services).page(
        _layer(services), FeatureQuery(limit=2, encoding="wkt")
    )

    assert _point_ids(page) == [1, 2]
    assert page.truncated is True
    assert page.next_cursor == "2"

    rest = _features(services).page(
        _layer(services),
        FeatureQuery(limit=2, encoding="wkt", cursor=page.next_cursor),
    )
    assert _point_ids(rest) == [3]
    assert rest.truncated is False
    assert rest.next_cursor is None


def test_the_same_query_over_the_same_data_returns_the_same_page(
    services: Services,
) -> None:
    """Deterministic means byte-for-byte, not "the same ids in some order"."""
    first = _features(services).page(
        _layer(services), FeatureQuery(limit=3, encoding="wkt")
    )
    second = _features(services).page(
        _layer(services), FeatureQuery(limit=3, encoding="wkt")
    )

    assert first.to_wire() == second.to_wire()


def test_a_page_smaller_than_the_layer_is_all_of_it(services: Services) -> None:
    page = _features(services).page(
        _layer(services), FeatureQuery(limit=10, encoding="wkt")
    )

    assert _point_ids(page) == [1, 2, 3]
    assert page.truncated is False


def test_a_page_over_the_ceiling_is_refused_before_the_provider_sees_it(
    services: Services,
) -> None:
    from qgis_sdk.models import MAX_FEATURE_PAGE

    with pytest.raises(ValueError, match=str(MAX_FEATURE_PAGE)):
        FeatureQuery(limit=MAX_FEATURE_PAGE + 1)


def test_ids_narrow_a_page_without_an_expression(services: Services) -> None:
    page = _features(services).page(
        _layer(services), FeatureQuery(limit=10, encoding="wkt", ids=(3, 1))
    )

    # Which ids come back is the contract; the order an explicit id set comes
    # back in is the provider's, and asking for it here would pin a detail the
    # paging tests already cover for a cursor walk.
    assert sorted(_point_ids(page)) == [1, 3]


def test_a_bbox_filter_runs_in_the_provider(services: Services) -> None:
    """Only the first two points fall inside this box."""
    page = _features(services).page(
        _layer(services),
        FeatureQuery(limit=10, encoding="wkt", bbox=(20.9, 51.9, 21.15, 52.15)),
    )

    assert _point_ids(page) == [1, 2]


def test_an_expression_filter_runs_in_the_provider(services: Services) -> None:
    page = _features(services).page(
        _layer(services),
        FeatureQuery(limit=10, encoding="wkt", expression='"id" > 1'),
    )

    assert _point_ids(page) == [2, 3]


def test_an_unknown_layer_is_reported_by_its_identifier(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        _features(services).page("no-such-layer", FeatureQuery(limit=1, encoding="wkt"))

    assert error.value.identifier == "no-such-layer"


# -- one feature -------------------------------------------------------------


def test_one_feature_carries_its_attributes_and_geometry(services: Services) -> None:
    feature = _features(services).feature(_layer(services), 2, encoding="wkt")

    assert feature.id == 2
    assert feature.attributes["value"] == "b"
    assert feature.geometry is not None
    assert feature.geometry.encoding == "wkt"
    assert feature.geometry.geometry_type == "point"
    assert feature.geometry.is_empty is False
    assert feature.geometry.value


def test_a_row_with_no_shape_reports_a_geometry_that_says_so(
    services: Services,
) -> None:
    """Missing and empty are different facts, and neither is "not asked for".

    A row added without a geometry - a record a page created from a form, say -
    has no shape of its own. ``Feature.geometry`` is ``None`` when the query did
    not ask for one, so a page that asked and got ``None`` would be reading an
    answer to a different question.
    """
    assert services.editable_layer is not None
    layer_id = services.editable_layer()
    features = _features(services)

    session = features.begin_edit(layer_id)
    try:
        session.add({"id": 77, "value": "shapeless"})
        session.commit()
    finally:
        session.close()

    page = features.page(
        layer_id,
        FeatureQuery(limit=10, encoding="wkt", expression="\"value\" = 'shapeless'"),
    )
    shapeless = _only(page)

    assert shapeless.geometry is not None
    assert shapeless.geometry.geometry_type == "none"
    assert shapeless.geometry.value == ""
    assert shapeless.geometry.part_count == 0
    assert shapeless.geometry.vertex_count == 0
    assert shapeless.geometry.is_empty is False

    # Asking for no geometry is the case `None` answers.
    bare = _only(
        features.page(
            layer_id,
            FeatureQuery(
                limit=10,
                encoding="wkt",
                expression="\"value\" = 'shapeless'",
                with_geometry=False,
            ),
        )
    )
    assert bare.geometry is None


def test_a_feature_asked_for_without_geometry_has_none(services: Services) -> None:
    page = _features(services).page(
        _layer(services),
        FeatureQuery(limit=1, encoding="wkt", with_geometry=False),
    )

    assert page.items[0].geometry is None


def test_an_unknown_feature_is_reported_by_its_identifier(
    services: Services,
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        _features(services).feature(_layer(services), 999)

    assert "999" in error.value.identifier


# -- expressions -------------------------------------------------------------


def test_an_expression_is_a_value_or_a_message(services: Services) -> None:
    value = _features(services).evaluate(
        '"id" > 1', layer_id=_layer(services), feature_id=3
    )
    broken = _features(services).evaluate("1 +", layer_id=_layer(services))

    assert value.valid is True
    # Truthiness, not identity: QGIS's expression engine has no boolean type and
    # answers a comparison with 1, while the fake answers what a Python caller
    # expects. A page tests the value, not its spelling.
    assert bool(value.value) is True
    assert value.message is None
    assert broken.valid is False
    assert broken.message


def test_validate_names_the_columns_an_expression_reads(services: Services) -> None:
    check = _features(services).check('"id" > 1', layer_id=_layer(services))

    assert check.valid is True
    assert check.referenced_columns == ("id",)


def test_an_expression_the_backend_cannot_parse_is_reported_not_raised(
    services: Services,
) -> None:
    """A syntax error is an answer: ``valid`` false with the message."""
    outcome = _features(services).evaluate("this is not an expression")

    assert outcome.valid is False
    assert outcome.value is None
    assert outcome.message


# -- editing -----------------------------------------------------------------


def _only(page) -> object:
    """The single feature of a page, so a test says which row it means."""
    assert len(page.items) == 1, [feature.id for feature in page.items]
    return page.items[0]


def test_an_editing_session_writes_on_commit_and_discards_on_rollback(
    services: Services,
) -> None:
    assert services.editable_layer is not None
    layer_id = services.editable_layer()
    features = _features(services)

    session = features.begin_edit(layer_id)
    try:
        added = session.add({"id": 9, "value": "z"})
        assert session.pending == 1
        outcome = session.commit()
    finally:
        session.close()

    assert outcome.committed is True
    assert outcome.applied == 1
    # `feature_ids` names the ids the buffer held, which is what `add` returned.
    assert added in outcome.feature_ids
    # That id is not promised to be the stored one, though: QGIS renumbers an
    # added feature from the provider at commit, and the fake does not. The
    # contract asks the layer for the row it wrote instead of assuming the two
    # agree (doc-12).
    written = _only(
        features.page(
            layer_id,
            FeatureQuery(limit=10, encoding="wkt", expression="\"value\" = 'z'"),
        )
    )
    assert written.attributes["value"] == "z"
    assert written.attributes["id"] == 9

    second = features.begin_edit(layer_id)
    try:
        second.delete(written.id)
        assert second.pending == 1
        second.rollback()
        assert second.pending == 0
        assert features.feature(layer_id, written.id).attributes["value"] == "z"
    finally:
        second.close()


def test_a_second_begin_returns_the_open_session(services: Services) -> None:
    """Two buffers over one layer is a race the caller cannot see."""
    assert services.editable_layer is not None
    features = _features(services)
    layer_id = services.editable_layer()

    first = features.begin_edit(layer_id)
    try:
        assert features.begin_edit(layer_id) is first
    finally:
        first.close()


def test_editing_an_unknown_layer_is_refused_by_name(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        _features(services).begin_edit("no-such-layer")
