"""Contract: an operation produces a new layer and never edits its source.

Runs against both backends, like the rest of this directory. Two things are
deliberately *not* asserted here because the in-memory double cannot know them:
whether a working CRS is projected, and whether its units are metres. Those need
a CRS database, so they are the native adapter's own tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    QgisSdkLayerNotFoundError,
    VectorLayerInfo,
)

if TYPE_CHECKING:
    from .conftest import Services


def _buffer(
    services: Services, layer_id: str, distance: float = 500.0
) -> VectorLayerInfo:
    return services.algorithms.execute(
        BufferRequest(
            layer_id=layer_id,
            distance_metres=distance,
            working_crs=services.working_crs,
        )
    )


def test_buffering_produces_a_new_polygon_layer(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)

    output = _buffer(services, source.id)

    assert output.id != source.id
    assert output.geometry_type == "polygon"
    assert output.crs == services.working_crs
    # Attributes are carried over, not the field list: a driver may add its own
    # identifier column (GeoPackage writes an ``fid``), and that is not a
    # contract violation - losing ``value`` would be.
    assert set(source.field_names) <= set(output.field_names)


def test_the_source_layer_is_unchanged_by_the_operation(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)

    _buffer(services, source.id)

    assert services.layers.layer(source.id) == source
    assert source.id in [layer.id for layer in services.layers.list_layers()]


def test_the_output_is_a_layer_the_runtime_owns(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)
    output = _buffer(services, source.id)

    services.project.add_layer(output.id)

    assert services.project.layer_ids() == (output.id,)


def test_centroids_need_no_working_crs(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)

    output = services.algorithms.execute(CentroidRequest(layer_id=source.id))

    assert (output.geometry_type, output.id != source.id) == ("point", True)


def test_each_execution_produces_its_own_layer(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)

    first = _buffer(services, source.id)
    second = _buffer(services, source.id)

    assert first.id != second.id
    assert {first.id, second.id} <= {
        layer.id for layer in services.layers.list_layers()
    }


def test_an_unknown_layer_is_refused(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        _buffer(services, "no-such-layer")


def test_nothing_is_added_to_the_project_by_the_operation_itself(
    services: Services,
) -> None:
    source = services.layers.open_vector(services.dataset)

    _buffer(services, source.id)

    assert services.project.layer_ids() == ()
