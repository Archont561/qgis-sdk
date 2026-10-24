"""Contract: services refuse work once their owning scope is closed."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import QgisSdkScopeClosedError

if TYPE_CHECKING:
    from .conftest import Services


def test_opening_a_layer_after_the_owner_closed_is_refused(
    services: Services,
) -> None:
    services.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        services.layers.open_vector(services.dataset)


def test_listing_layers_after_the_owner_closed_is_refused(
    services: Services,
) -> None:
    services.layers.open_vector(services.dataset)
    services.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        services.layers.list_layers()


def test_reading_one_layer_after_the_owner_closed_is_refused(
    services: Services,
) -> None:
    info = services.layers.open_vector(services.dataset)
    services.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        services.layers.layer(info.id)


def test_reading_a_selection_after_the_owner_closed_is_refused(
    services: Services,
) -> None:
    info = services.layers.open_vector(services.dataset)
    services.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        services.layers.selection(info.id)


def test_project_membership_after_the_owner_closed_is_refused(
    services: Services,
) -> None:
    info = services.layers.open_vector(services.dataset)
    services.project.add_layer(info.id)
    services.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        services.project.layer_ids()


def test_adding_to_the_project_after_the_owner_closed_is_refused(
    services: Services,
) -> None:
    info = services.layers.open_vector(services.dataset)
    services.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        services.project.add_layer(info.id)


def test_closing_the_owner_scope_twice_is_safe(services: Services) -> None:
    services.scope.close()
    services.scope.close()
