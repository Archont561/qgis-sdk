"""Real QGIS: a plugin's providers appear in Processing while it runs, and execute.

This is the acceptance test for TASK-39 and TASK-63. A ``@plugin`` class lists
``qgis_sdk.reference``'s provider; starting its runtime over the native context
puts ``reference:buffer`` in ``QgsApplication.processingRegistry()``, running it
through ``processing.run`` the way a user or the modeler would goes through the
same ``invoke`` an action uses, and unloading removes it again. Then the two
things decision-19 cares about: the source is untouched and the produced layer
really arrived in the destination the caller asked for.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from qgis_sdk import plugin
from qgis_sdk.algorithms import describe_algorithm
from qgis_sdk.core import AlgorithmContext, PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.models import CentroidRequest, LayerInput, VectorLayerInfo
from qgis_sdk.providers import Provider
from qgis_sdk.reference import buffer_layer, reference_provider

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _processing(native_services: Services):
    """The ``ctx.processing`` service a QGIS host builds over these services."""
    # The fixture starts QGIS; the adapters below must be imported after it.
    from qgis_sdk.adapters.qgis import NativeProcessing

    return NativeProcessing(
        layers=native_services.layers,
        algorithms=native_services.algorithms,
        project=native_services.project,
        scope=native_services.scope,
    )


def _runtime(native_services: Services, plugin_class: type) -> PluginRuntime:
    context = PluginContext(
        notifications=native_services.notifications,
        scope=native_services.scope.child(),
        layers=native_services.layers,
        project=native_services.project,
        algorithms=native_services.algorithms,
        processing=_processing(native_services),
    )
    return PluginRuntime(plugin_class, context)


@plugin(id="reference_owner", title="Reference owner")
class ReferenceOwner:
    """The one line a plugin writes to put its algorithms in the toolbox."""

    providers = (reference_provider,)


@pytest.fixture
def running(native_services: Services):
    """Start a plugin that lists the reference provider; always unload it."""
    runtime = _runtime(native_services, ReferenceOwner)
    runtime.start()
    try:
        yield runtime
    finally:
        runtime.unload()


def _algorithm_ids(provider_id: str) -> list[str]:
    from qgis.core import QgsApplication

    registry = QgsApplication.processingRegistry()
    return sorted(
        algorithm.id()
        for algorithm in registry.algorithms()
        if algorithm.provider() is not None and algorithm.provider().id() == provider_id
    )


def test_start_advertises_the_provider_with_both_algorithms(running) -> None:
    assert running.registered_providers == ("reference",)
    assert _algorithm_ids("reference") == ["reference:buffer", "reference:centroid"]


def test_unload_removes_the_algorithms_again(native_services: Services) -> None:
    runtime = _runtime(native_services, ReferenceOwner)
    runtime.start()
    assert _algorithm_ids("reference")

    runtime.unload()

    assert _algorithm_ids("reference") == []
    assert runtime.registered_providers == ()


def test_the_registered_algorithm_reports_the_declared_metadata(running) -> None:
    from qgis.core import QgsApplication

    algorithm = QgsApplication.processingRegistry().algorithmById("reference:buffer")

    assert algorithm is not None
    assert algorithm.displayName() == "Buffer a layer in an explicit working CRS"
    assert algorithm.group() == "Geometry"
    assert algorithm.provider().name() == "Reference plugin"


def test_the_algorithm_declares_no_threading_because_none_is_qualified(
    running,
) -> None:
    from qgis.core import QgsApplication, QgsProcessingAlgorithm

    algorithm = QgsApplication.processingRegistry().algorithmById("reference:buffer")

    assert algorithm.flags() & QgsProcessingAlgorithm.FlagNoThreading


def test_the_parameters_follow_the_functions_inputs(running) -> None:
    from qgis.core import QgsApplication

    algorithm = QgsApplication.processingRegistry().algorithmById("reference:buffer")
    names = [parameter.name() for parameter in algorithm.parameterDefinitions()]

    assert names == ["layer_id", "distance_metres", "working_crs", "OUTPUT"]
    assert describe_algorithm(buffer_layer).kinds == {
        "layer_id": "layer",
        "distance_metres": "metres",
        "working_crs": "crs",
    }


def test_running_through_processing_writes_the_requested_output(
    running, native_services: Services, tmp_path: Path
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
    running, native_services: Services, tmp_path: Path
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
    running, native_services: Services, tmp_path: Path
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


def test_a_second_plugin_with_the_same_provider_id_is_refused_by_name(
    running, native_services: Services
) -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    twin = Provider(id="reference", title="Another reference")

    @plugin(id="twin", title="Twin")
    class Twin:
        providers = (twin,)

    other = _runtime(native_services, Twin)
    with pytest.raises(QgisSdkDeclarationError, match="'reference' is already"):
        other.start()

    assert _algorithm_ids("reference") == ["reference:buffer", "reference:centroid"]


def test_the_toolbox_calls_the_function_through_the_same_context_type(
    running, native_services: Services, tmp_path: Path
) -> None:
    """A provider a plugin declares itself runs exactly like the shipped one."""
    from qgis import processing
    from qgis.core import QgsVectorLayer

    seen: list[AlgorithmContext] = []
    provider = Provider(id="usertest", title="User test provider")

    @provider.algorithm(id="copy", title="Copy layer")
    def copy_layer(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
        seen.append(ctx)
        return ctx.algorithms.execute(CentroidRequest(layer_id))

    @plugin(id="user", title="User plugin")
    class UserPlugin:
        providers = (provider,)

    runtime = _runtime(native_services, UserPlugin)
    runtime.start()
    try:
        assert _algorithm_ids("usertest") == ["usertest:copy"]
        destination = tmp_path / "user-copy.gpkg"
        result = processing.run(
            "usertest:copy",
            {"layer_id": str(native_services.dataset), "OUTPUT": str(destination)},
        )
        assert QgsVectorLayer(result["OUTPUT"], "x", "ogr").featureCount() == 3
    finally:
        runtime.unload()

    assert len(seen) == 1
    assert isinstance(seen[0], AlgorithmContext)
    assert seen[0].algorithms is native_services.algorithms
    assert seen[0].scope.closed
    assert _algorithm_ids("usertest") == []


def test_a_plugin_over_a_context_without_processing_registers_nothing(
    native_services: Services,
) -> None:
    context = PluginContext(
        notifications=native_services.notifications,
        scope=ResourceScope(),
        algorithms=native_services.algorithms,
    )
    runtime = PluginRuntime(ReferenceOwner, context)

    runtime.start()
    try:
        assert runtime.registered_providers == ()
        assert _algorithm_ids("reference") == []
    finally:
        runtime.unload()
