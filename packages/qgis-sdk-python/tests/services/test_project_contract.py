"""Contract: project membership changes only when the caller asks for it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import QgisSdkLayerNotFoundError

if TYPE_CHECKING:
    from .conftest import Services


def test_project_starts_without_layers(services: Services) -> None:
    assert services.project.layer_ids() == ()


def test_added_layer_appears_on_the_project(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    services.project.add_layer(info.id)

    assert info.id in services.project.layer_ids()


def test_adding_the_same_layer_twice_keeps_one_entry(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    services.project.add_layer(info.id)
    services.project.add_layer(info.id)

    assert services.project.layer_ids() == (info.id,)


def test_project_refuses_a_layer_the_runtime_does_not_own(
    services: Services,
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        services.project.add_layer("no-such-layer")

    assert error.value.identifier == "no-such-layer"
