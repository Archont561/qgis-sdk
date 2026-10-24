"""Contract: a packaged style applies only to a layer it can express."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    QgisSdkLayerNotFoundError,
    QgisSdkStyleIncompatibleError,
)

if TYPE_CHECKING:
    from .conftest import Services


def test_packaged_style_applies_to_a_compatible_layer(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    services.styles.apply_style(info.id, services.compatible_style)


def test_style_for_an_unknown_layer_is_refused(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        services.styles.apply_style("no-such-layer", services.compatible_style)


def test_incompatible_style_names_the_mismatch(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    with pytest.raises(QgisSdkStyleIncompatibleError) as error:
        services.styles.apply_style(info.id, services.incompatible_style)

    assert error.value.layer_id == info.id
    assert error.value.style == services.incompatible_style
    assert error.value.reasons, "a refusal must say what did not fit"
    assert error.value.code == "style_incompatible"
