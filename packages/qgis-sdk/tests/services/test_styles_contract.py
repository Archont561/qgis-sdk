"""Contract: a packaged style applies only where its reviewed target matches.

The style identifiers are catalog identifiers shipped with the package, not
fixture-local names, so both backends are held to the same reviewed resources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    QgisSdkLayerNotFoundError,
    QgisSdkStyleIncompatibleError,
    QgisSdkStyleNotFoundError,
)

if TYPE_CHECKING:
    from .conftest import Services


def test_packaged_style_applies_to_a_compatible_layer(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    services.styles.apply_style(info.id, services.compatible_style)


def test_style_for_an_unknown_layer_is_refused(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        services.styles.apply_style("no-such-layer", services.compatible_style)


def test_unknown_style_identifier_is_refused(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    with pytest.raises(QgisSdkStyleNotFoundError) as error:
        services.styles.apply_style(info.id, "reference/not-a-style")

    assert error.value.style == "reference/not-a-style"
    assert error.value.code == "style_not_found"


def test_geometry_mismatch_is_refused_and_names_the_geometry(
    services: Services,
) -> None:
    lines = services.layers.open_vector(services.line_dataset)

    with pytest.raises(QgisSdkStyleIncompatibleError) as error:
        services.styles.apply_style(lines.id, services.compatible_style)

    assert error.value.layer_id == lines.id
    assert error.value.style == services.compatible_style
    assert error.value.code == "style_incompatible"
    assert any("point" in reason for reason in error.value.reasons)


def test_missing_field_is_refused_and_names_the_field(services: Services) -> None:
    minimal = services.layers.open_vector(services.minimal_dataset)

    with pytest.raises(QgisSdkStyleIncompatibleError) as error:
        services.styles.apply_style(minimal.id, services.compatible_style)

    assert any("value" in reason for reason in error.value.reasons)


def test_every_mismatch_is_reported_at_once(services: Services) -> None:
    # Wrong geometry and a missing required field: the caller should not need one
    # round trip per problem.
    lines = services.layers.open_vector(services.line_dataset)

    with pytest.raises(QgisSdkStyleIncompatibleError) as error:
        services.styles.apply_style(lines.id, services.compatible_style)

    assert len(error.value.reasons) == 2


def test_a_style_for_another_geometry_applies_to_that_geometry(
    services: Services,
) -> None:
    lines = services.layers.open_vector(services.line_dataset)

    services.styles.apply_style(lines.id, services.incompatible_style)
