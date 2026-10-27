"""``FakeAlgorithms.run``: scripted answers, recorded runs, the real validation.

Pure. The contract suite proves parity with the native adapter; this file
proves what only the fake offers a test author: scripting, recording and
the honest refusal when nothing was scripted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRun,
    Catalogue,
    FileRef,
    OutputInfo,
    ParameterInfo,
    ProviderInfo,
    QgisSdkAlgorithmFailedError,
    QgisSdkAlgorithmNotFoundError,
    QgisSdkScopeClosedError,
)
from qgis_sdk.processing import native
from qgis_sdk.testing import FakeAlgorithms, FakeFiles, FakeLayers

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reference"
POINTS = FIXTURES / "points.geojson"
LINES = FIXTURES / "lines.geojson"


@pytest.fixture
def world():
    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(POINTS, name="points", geometry_type="point", field_names=("id",))
    layers.register(LINES, name="lines", geometry_type="line", field_names=("id",))
    files = FakeFiles(scope)
    return scope, layers, files, FakeAlgorithms(layers, scope, files=files)


def test_list_and_describe_read_the_shipped_snapshot(world) -> None:
    _, _, _, algorithms = world

    assert {p.id for p in algorithms.providers()} == {
        "native",
        "qgis",
        "gdal",
        "3d",
        "pdal",
    }
    assert len(algorithms.list()) == sum(
        len(algorithms.list(p.id)) for p in algorithms.providers()
    )
    assert algorithms.describe("gdal:translate").provider == "gdal"
    assert algorithms.list("grass") == ()
    with pytest.raises(QgisSdkAlgorithmNotFoundError):
        algorithms.describe("grass:r.buffer")


def test_a_test_can_bring_its_own_catalogue(world) -> None:
    scope, layers, _, _ = world
    catalogue = Catalogue(
        qgis_version="x",
        providers=(ProviderInfo(id="saga"),),
        algorithms=(
            AlgorithmInfo(
                id="saga:slope",
                provider="saga",
                name="slope",
                label="Slope",
                parameters=(ParameterInfo(name="ELEVATION", kind="raster"),),
                outputs=(OutputInfo(name="SLOPE", kind="outputRaster"),),
            ),
        ),
    )
    algorithms = FakeAlgorithms(layers, scope, catalogue=catalogue)
    algorithms.script_run("saga:slope", {"SLOPE": POINTS})

    result = algorithms.run("saga:slope", {"ELEVATION": str(POINTS)})

    assert isinstance(result.file("SLOPE"), FileRef)
    with pytest.raises(QgisSdkAlgorithmNotFoundError):
        algorithms.describe("native:buffer")


def test_runs_are_recorded_and_answered_in_script_order(world) -> None:
    _, layers, _, algorithms = world
    points = layers.open_vector(POINTS)
    algorithms.script_run("native:centroids", {"OUTPUT": LINES}, repeat=False)
    algorithms.script_run("native:centroids", {"OUTPUT": POINTS})

    first = algorithms.run(native.Centroids(input=points.id))
    second = algorithms.run("native:centroids", {"INPUT": points.id})
    third = algorithms.run(AlgorithmRun("native:centroids", {"INPUT": points.id}))

    assert [r.vector("OUTPUT").name for r in (first, second, third)] == [
        "lines",
        "points",
        "points",
    ]
    assert (
        algorithms.runs == [AlgorithmRun("native:centroids", {"INPUT": points.id})] * 3
    )


def test_a_callable_script_sees_the_run(world) -> None:
    _, layers, files, algorithms = world
    points = layers.open_vector(POINTS)
    algorithms.script_run(
        "native:buffer",
        lambda run: {"OUTPUT": LINES, "DISTANCE_SEEN": run.params["DISTANCE"]},
    )

    result = algorithms.run("native:buffer", {"INPUT": points.id, "DISTANCE": 12.5})

    assert result.value("DISTANCE_SEEN") == 12.5
    assert result.vector("OUTPUT").name == "lines"
    assert files.granted == ()


def test_a_run_nobody_scripted_fails_honestly(world) -> None:
    _, layers, _, algorithms = world
    points = layers.open_vector(POINTS)

    with pytest.raises(QgisSdkAlgorithmFailedError, match="script_run"):
        algorithms.run("native:buffer", {"INPUT": points.id})

    # Recorded anyway: the test can still see what the workflow asked for.
    assert algorithms.runs[0].algorithm == "native:buffer"


def test_file_outputs_are_minted_through_the_files_service(world) -> None:
    _, layers, files, algorithms = world
    points = layers.open_vector(POINTS)
    algorithms.script_run(
        "native:basicstatisticsforfields",
        {"COUNT": 3, "OUTPUT_HTML_FILE": LINES, "OUTPUT": POINTS},
    )

    result = algorithms.run(
        "native:basicstatisticsforfields",
        {"INPUT_LAYER": points.id, "FIELD_NAME": "id"},
    )

    ref = result.file("OUTPUT_HTML_FILE")
    assert files.resolve(ref) == LINES.resolve()
    assert ref in files.granted
    assert result.vector("OUTPUT").name == "points"
    assert {"name": "COUNT", "kind": "value", "value": 3} in result.to_wire()["outputs"]


def test_a_closed_scope_refuses_everything(world) -> None:
    scope, _, _, algorithms = world
    scope.close()

    for call in (
        lambda: algorithms.list(),
        lambda: algorithms.describe("native:buffer"),
        lambda: algorithms.run("native:buffer", {"INPUT": "x"}),
    ):
        with pytest.raises(QgisSdkScopeClosedError):
            call()
