"""Contract: reading layers and selections through the injected service."""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import QgisSdkLayerNotFoundError

if TYPE_CHECKING:
    Services = conftest.Services


def test_open_vector_describes_the_layer_it_loaded(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    assert info.id, "an opened layer must carry a stable identifier"
    assert info.name == conftest.FIXTURE_NAME
    assert info.geometry_type == conftest.FIXTURE_GEOMETRY
    assert info.field_names == conftest.FIXTURE_FIELDS
    assert info.crs == conftest.FIXTURE_CRS


def test_opened_layer_is_listed_and_looked_up_by_id(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    assert info in services.layers.list_layers()
    assert services.layers.layer(info.id) == info


def test_unknown_layer_identifier_is_reported(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        services.layers.layer("no-such-layer")

    assert error.value.identifier == "no-such-layer"


def test_unreadable_dataset_is_reported_as_a_missing_layer(
    services: Services,
) -> None:
    absent = services.dataset.with_name("absent.geojson")

    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        services.layers.open_vector(absent)

    assert "absent.geojson" in error.value.identifier


def test_selection_reports_the_selected_feature_ids(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)
    services.select(info.id, (3, 1))

    assert sorted(services.layers.selection(info.id)) == [1, 3]


def test_layer_without_a_selection_reports_an_empty_selection(
    services: Services,
) -> None:
    info = services.layers.open_vector(services.dataset)

    assert services.layers.selection(info.id) == ()


def test_selection_of_an_unknown_layer_is_refused(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        services.layers.selection("no-such-layer")
