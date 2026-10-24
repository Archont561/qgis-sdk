"""Real QGIS: a declared provider's algorithms appear and execute in Processing.

This is the acceptance test for TASK-39. It registers ``qgis_sdk.reference``'s
provider with QGIS, checks the registry advertises ``reference:buffer``, runs it
through ``processing.run`` the way a user or the modeler would, and then checks
the two things decision-19 cares about: the source is untouched and the produced
layer really arrived in the destination the caller asked for.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import pytest
from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    LayerInput,
    VectorLayerInfo,
)
from qgis_sdk.providers import Provider, parameter_kinds
from qgis_sdk.reference import reference_provider

if TYPE_CHECKING:
    from .conftest import Services


@dataclass(frozen=True, slots=True)
class PassThroughRequest:
    """A request a test provider declares, streamed straight to the centroid op.

    The marker is what makes the field a layer picker; a plain ``str`` would
    arrive as free text and the layers service would refuse the path.
    """

    layer_id: Annotated[str, LayerInput()]


@dataclass(frozen=True, slots=True)
class PassThroughResult:
    output: VectorLayerInfo


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def registered(native_services: Services, tmp_path: Path):
    """Register the reference provider and always remove it again."""
    from qgis_sdk.adapters.qgis import register_provider

    # The fixture starts QGIS; the adapters below must be imported after it.
    bridge = register_provider(
        reference_provider,
        layers=native_services.layers,
        algorithms=native_services.algorithms,
        project=native_services.project,
        scope=native_services.scope,
    )
    try:
        yield bridge
    finally:
        bridge.unregister()


def _algorithm_ids(provider_id: str) -> list[str]:
    from qgis.core import QgsApplication

    registry = QgsApplication.processingRegistry()
    return sorted(
        algorithm.id()
        for algorithm in registry.algorithms()
        if algorithm.provider() is not None and algorithm.provider().id() == provider_id
    )


def test_the_provider_is_advertised_with_both_algorithms(registered) -> None:
    assert _algorithm_ids("reference") == ["reference:buffer", "reference:centroid"]


def test_the_registered_algorithm_reports_the_declared_metadata(registered) -> None:
    from qgis.core import QgsApplication

    algorithm = QgsApplication.processingRegistry().algorithmById("reference:buffer")

    assert algorithm is not None
    assert algorithm.displayName() == "Buffer a layer in an explicit working CRS"
    assert algorithm.group() == "Geometry"
    assert algorithm.provider().name() == "Reference plugin"


def test_the_algorithm_declares_no_threading_because_none_is_qualified(
    registered,
) -> None:
    from qgis.core import QgsApplication, QgsProcessingAlgorithm

    algorithm = QgsApplication.processingRegistry().algorithmById("reference:buffer")

    assert algorithm.flags() & QgsProcessingAlgorithm.FlagNoThreading


def test_the_parameters_follow_the_request_dataclass(registered) -> None:
    from qgis.core import QgsApplication

    algorithm = QgsApplication.processingRegistry().algorithmById("reference:buffer")
    names = [parameter.name() for parameter in algorithm.parameterDefinitions()]

    assert names == ["layer_id", "distance_metres", "working_crs", "OUTPUT"]
    kinds = dict(parameter_kinds(BufferRequest))
    assert kinds == {
        "layer_id": "layer",
        "distance_metres": "metres",
        "working_crs": "crs",
    }


def test_running_through_processing_writes_the_requested_output(
    registered, native_services: Services, tmp_path: Path
) -> None:
    from qgis import processing
    from qgis.core import QgsVectorLayer

    destination = tmp_path / "toolbox-buffer.gpkg"
    before = _digest(native_services.dataset)

    result = processing.run(
        "reference:buffer",
        {
            "layer_id": str(native_services.dataset),
            "distance_metres": 250.0,
            "working_crs": native_services.working_crs,
            "OUTPUT": str(destination),
        },
    )

    produced = QgsVectorLayer(result["OUTPUT"], "produced", "ogr")
    assert produced.isValid()
    assert produced.featureCount() == 3
    assert produced.crs().authid() == native_services.working_crs
    assert _digest(native_services.dataset) == before


def test_a_run_does_not_add_its_output_to_the_project(
    registered, native_services: Services, tmp_path: Path
) -> None:
    """QGIS owns the destination here, so the bridge must not add a second layer."""
    from qgis import processing

    processing.run(
        "reference:centroid",
        {
            "layer_id": str(native_services.dataset),
            "OUTPUT": str(tmp_path / "centroid.gpkg"),
        },
    )

    assert native_services.project.layer_ids() == ()


def test_a_refused_request_surfaces_as_a_processing_error(
    registered, native_services: Services, tmp_path: Path
) -> None:
    from qgis import processing

    with pytest.raises(Exception) as error:
        processing.run(
            "reference:buffer",
            {
                "layer_id": str(native_services.dataset),
                "distance_metres": 250.0,
                "working_crs": "EPSG:4326",
                "OUTPUT": str(tmp_path / "never.gpkg"),
            },
        )

    assert "geographic" in str(error.value)
    assert not (tmp_path / "never.gpkg").exists()


def test_unregistering_removes_the_algorithms(native_services: Services) -> None:
    from qgis_sdk.adapters.qgis import register_provider

    bridge = register_provider(
        reference_provider,
        layers=native_services.layers,
        algorithms=native_services.algorithms,
        project=native_services.project,
        scope=native_services.scope,
    )
    assert _algorithm_ids("reference")

    bridge.unregister()

    assert _algorithm_ids("reference") == []


def test_a_second_registration_of_the_same_provider_is_refused(
    registered, native_services: Services
) -> None:
    from qgis_sdk.adapters.qgis import register_provider
    from qgis_sdk.declarations import QgisSdkDeclarationError

    with pytest.raises(QgisSdkDeclarationError, match="already registered"):
        register_provider(
            reference_provider,
            layers=native_services.layers,
            algorithms=native_services.algorithms,
            project=native_services.project,
            scope=native_services.scope,
        )


def test_a_user_declared_provider_runs_the_same_way(
    registered, native_services: Services, tmp_path: Path
) -> None:
    """A provider a plugin declares itself behaves exactly like the shipped one."""
    from qgis.core import QgsApplication
    from qgis_sdk.adapters.qgis import register_provider

    provider = Provider(id="usertest", title="User test provider")

    @provider.algorithm(id="copy", title="Copy layer")
    class Copy:
        def __init__(self, ctx) -> None:
            self.ctx = ctx

        def run(self, inputs: PassThroughRequest) -> PassThroughResult:
            return PassThroughResult(
                output=self.ctx.algorithms.execute(CentroidRequest(inputs.layer_id))
            )

    bridge = register_provider(
        provider,
        layers=native_services.layers,
        algorithms=native_services.algorithms,
        project=native_services.project,
        scope=native_services.scope,
    )
    try:
        assert _algorithm_ids("usertest") == ["usertest:copy"]
        from qgis import processing
        from qgis.core import QgsVectorLayer

        destination = tmp_path / "user-copy.gpkg"
        result = processing.run(
            "usertest:copy",
            {"layer_id": str(native_services.dataset), "OUTPUT": str(destination)},
        )
        assert QgsVectorLayer(result["OUTPUT"], "x", "ogr").featureCount() == 3
    finally:
        QgsApplication.processingRegistry().removeProvider(bridge)
