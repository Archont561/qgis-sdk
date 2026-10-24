"""Real Processing: source preservation, metres, cleanup and project addition.

These run only under ``QGIS_SDK_NATIVE_SERVICES=1`` with QGIS installed, because
each assertion is about behaviour that cannot be faked honestly: that QGIS
Processing left the dataset on disk untouched, that ``distance_metres`` really
became metres, that a failed run removed what it wrote, and that the produced
file became a project layer through PyQGIS.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    QgisSdkAlgorithmRejectedError,
    QgisSdkLayerNotFoundError,
    VectorLayerInfo,
)

if TYPE_CHECKING:
    from .conftest import Services

# A projected CRS whose map units are US survey feet: a distance in metres would
# be silently wrong there, which is the case the adapter must refuse.
FEET_CRS = "EPSG:2227"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _width(path: Path) -> float:
    """Return a layer's extent width, in the units of its own CRS."""
    from qgis.core import QgsVectorLayer

    layer = QgsVectorLayer(str(path), "inspect", "ogr")
    assert layer.isValid()
    return layer.extent().width()


def test_the_source_dataset_is_byte_identical_after_a_buffer(
    native_services: Services,
) -> None:
    source = native_services.layers.open_vector(native_services.dataset)
    before = _digest(native_services.dataset)

    _buffer(native_services, source.id)

    assert _digest(native_services.dataset) == before


def test_the_source_layer_is_still_a_point_layer_afterwards(
    native_services: Services,
) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    output = _buffer(native_services, source.id)

    assert native_services.layers.layer(source.id) == source
    assert (source.geometry_type, output.geometry_type) == ("point", "polygon")


def test_the_distance_is_interpreted_in_metres(native_services: Services) -> None:
    """A buffer grows the extent by its distance on *both* sides.

    So two buffers 1000 m apart in distance must differ in width by 2000 m. This
    is the property that would break if the distance were applied in the source
    CRS: on a WGS 84 layer, 500 would then mean degrees and the two extents would
    be indistinguishable, while a feet-based CRS would be off by 3.28x.
    """
    source = native_services.layers.open_vector(native_services.dataset)

    _buffer(native_services, source.id, 500.0)
    _buffer(native_services, source.id, 1500.0)

    small, large = sorted(native_services.work_directory.rglob("buffer.gpkg"))
    difference = _width(large) - _width(small)

    assert abs(difference - 2000.0) < 2.0, difference


def test_a_geographic_working_crs_is_refused(native_services: Services) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        native_services.algorithms.execute(
            BufferRequest(
                layer_id=source.id, distance_metres=100.0, working_crs="EPSG:4326"
            )
        )

    assert "geographic" in error.value.reasons[0]
    assert error.value.request == "buffer"


def test_a_working_crs_with_non_metric_units_is_refused(
    native_services: Services,
) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        native_services.algorithms.execute(
            BufferRequest(
                layer_id=source.id, distance_metres=100.0, working_crs=FEET_CRS
            )
        )

    assert "metres" in error.value.reasons[0]


def test_an_unknown_working_crs_is_refused(native_services: Services) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        native_services.algorithms.execute(
            BufferRequest(
                layer_id=source.id, distance_metres=100.0, working_crs="EPSG:999999"
            )
        )

    assert "not a known CRS" in error.value.reasons[0]


def test_a_successful_run_keeps_only_its_output(native_services: Services) -> None:
    """The reprojection is scaffolding: it must not survive the run."""
    source = native_services.layers.open_vector(native_services.dataset)

    _buffer(native_services, source.id)

    names = sorted(
        path.name
        for path in native_services.work_directory.rglob("*")
        if path.is_file()
    )
    assert names == ["buffer.gpkg"]


def test_nothing_partial_survives_a_failure(native_services: Services) -> None:
    """A simulated mid-operation write followed by a failure leaves no file.

    QGIS raising after it had written part of an output could not be reproduced
    deterministically headlessly, so this drives the same cleanup path with a
    Processing stand-in that writes and then raises. The real failure path is
    covered by ``test_an_unknown_layer_is_refused_without_leaving_files``.
    """
    source = native_services.layers.open_vector(native_services.dataset)

    class FailingProcessing:
        def run(self, name: str, parameters: dict) -> None:
            Path(parameters["OUTPUT"]).write_bytes(b"partial output")
            raise RuntimeError("Processing failed after writing")

    # Imported here, not at module scope: the bindings path exists only after
    # the native fixture has started the application.
    from qgis_sdk.adapters.qgis import algorithms as adapter_module

    original = adapter_module._processing
    adapter_module._processing = lambda: FailingProcessing()
    try:
        with pytest.raises(RuntimeError, match="after writing"):
            _buffer(native_services, source.id)
    finally:
        adapter_module._processing = original

    assert list(native_services.work_directory.rglob("*")) == []


def test_an_unknown_layer_is_refused_without_leaving_files(
    native_services: Services,
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        _buffer(native_services, "no-such-layer")

    assert list(native_services.work_directory.rglob("*")) == []


def test_a_successful_execution_becomes_a_project_layer(
    native_services: Services,
) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    output = _buffer(native_services, source.id)
    native_services.project.add_layer(output.id)

    assert native_services.project.layer_ids() == (output.id,)
    assert native_services.project.layer_ids() != (source.id,)


def test_a_failed_execution_never_reaches_the_project(
    native_services: Services,
) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        native_services.algorithms.execute(
            BufferRequest(
                layer_id=source.id, distance_metres=100.0, working_crs="EPSG:4326"
            )
        )

    assert native_services.project.layer_ids() == ()


def test_centroids_run_without_a_working_crs(native_services: Services) -> None:
    source = native_services.layers.open_vector(native_services.dataset)

    output = native_services.algorithms.execute(CentroidRequest(layer_id=source.id))

    assert (output.geometry_type, output.crs) == ("point", source.crs)
