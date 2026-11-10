"""``FakeAlgorithms.run``: scripted answers, recorded runs, the real validation.

Pure. The contract suite proves parity with the native adapter; this file
proves what only the fake offers a test author: scripting, recording and
the honest refusal when nothing was scripted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.jobs import JobStatus
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
    QgisSdkAlgorithmRejectedError,
    QgisSdkJobCancelledError,
    QgisSdkScopeClosedError,
)
from qgis_sdk.processing import native
from qgis_sdk.testing import (
    FakeAlgorithms,
    FakeAlgorithmSetup,
    FakeFiles,
    FakeLayers,
    VectorLayerDeclaration,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reference"
POINTS = FIXTURES / "points.geojson"
LINES = FIXTURES / "lines.geojson"


@pytest.fixture
def world():
    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        VectorLayerDeclaration(
            POINTS, name="points", geometry_type="point", field_names=("id",)
        )
    )
    layers.register(
        VectorLayerDeclaration(
            LINES, name="lines", geometry_type="line", field_names=("id",)
        )
    )
    files = FakeFiles(scope)
    return (
        scope,
        layers,
        files,
        FakeAlgorithms(FakeAlgorithmSetup(layers, scope, files=files)),
    )


@pytest.mark.parametrize(
    "parameters,params",
    [
        ((ParameterInfo(name="../../outside", kind="sink"),), {}),
        ((ParameterInfo(name="OUTPUT", kind="sink", extension="../../evil"),), {}),
        ((ParameterInfo(name="CON", kind="sink"),), {}),
        (
            (
                ParameterInfo(name="OUT", kind="sink"),
                ParameterInfo(name="out", kind="sink"),
            ),
            {},
        ),
        (
            (
                ParameterInfo(name="A", kind="sink"),
                ParameterInfo(name="B", kind="sink"),
            ),
            {"A": "first.gpkg", "B": "second.gpkg"},
        ),
    ],
)
def test_unsafe_provider_destinations_are_refused_before_running(
    world, parameters, params
) -> None:
    scope, layers, _, _ = world
    info = AlgorithmInfo(
        id="test:unsafe",
        provider="test",
        name="unsafe",
        label="Unsafe",
        parameters=parameters,
    )
    algorithms = FakeAlgorithms(
        FakeAlgorithmSetup(
            layers, scope, catalogue=Catalogue(qgis_version="x", algorithms=(info,))
        )
    )
    called = []
    algorithms.script_run("test:unsafe", lambda run: called.append(run) or {})

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        algorithms.run("test:unsafe", params)

    assert called == []
    assert algorithms.runs == []


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
    algorithms = FakeAlgorithms(FakeAlgorithmSetup(layers, scope, catalogue=catalogue))
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


def test_a_fake_accepts_a_new_named_output_but_does_not_write_it(
    world, tmp_path: Path
) -> None:
    _, layers, _, algorithms = world
    points = layers.open_vector(POINTS)
    algorithms.script_run("native:centroids", {"OUTPUT": LINES})
    destination = tmp_path / "output.geojson"

    result = algorithms.run(
        "native:centroids", {"INPUT": points.id, "OUTPUT": str(destination)}
    )

    assert result.vector("OUTPUT").name == "lines"
    assert not destination.exists()
    assert algorithms.runs[-1].params["OUTPUT"] == str(destination)


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


# -- model runs and batches (TASK-94) ----------------------------------------

MODEL = FIXTURES / "report.model3"


def test_a_model_run_is_recorded_and_answered_from_the_script(world) -> None:
    _, layers, files, algorithms = world
    points = layers.open_vector(POINTS)
    model = files.grant_file(MODEL)
    algorithms.script_run_model(model, {"OUT": files.grant_file(LINES)})

    result = algorithms.run_model(model, {"FEATS": points.id})

    assert result.algorithm == model.name
    assert result.file("OUT").name == LINES.name
    assert [(ref.name, params) for ref, params in algorithms.model_runs] == [
        (model.name, {"FEATS": points.id})
    ]


def test_a_model_script_can_answer_per_run(world) -> None:
    _, _, files, algorithms = world
    model = files.grant_file(MODEL)
    algorithms.script_run_model(model, {"OUT": 1}, repeat=False)
    algorithms.script_run_model(model, {"OUT": 2}, repeat=False)

    first = algorithms.run_model(model, {})
    second = algorithms.run_model(model, {})

    assert (first.value("OUT"), second.value("OUT")) == (1, 2)
    with pytest.raises(QgisSdkAlgorithmFailedError):
        algorithms.run_model(model, {})


def test_an_unscripted_model_fails_honestly(world) -> None:
    _, _, files, algorithms = world
    model = files.grant_file(MODEL)

    with pytest.raises(QgisSdkAlgorithmFailedError) as failed:
        algorithms.run_model(model, {})

    assert "script_run_model" in failed.value.detail


def test_a_model_run_refuses_a_path(world) -> None:
    *_, algorithms = world

    with pytest.raises(QgisSdkAlgorithmRejectedError) as refused:
        algorithms.run_model(str(MODEL), {})

    assert "FileRef" in str(refused.value)


def _drive(algorithms, workers) -> None:
    service = algorithms.jobs
    service.tick()
    workers.run_all()
    service.tick()


def test_a_batch_runs_every_item_through_the_jobs_service(world) -> None:
    from qgis_sdk.testing import FakeWorkers

    scope, layers, files, _ = world
    points = layers.open_vector(POINTS)
    workers = FakeWorkers()
    algorithms = FakeAlgorithms(
        FakeAlgorithmSetup(layers, scope, files=files, workers=workers)
    )
    algorithms.script_run("native:buffer", {"OUTPUT": POINTS})

    handle = algorithms.batch([native.Buffer(input=points.id) for _ in range(3)])
    assert handle.description.title == "Run algorithm batch"

    _drive(algorithms, workers)
    results = handle.result

    assert len(results) == 3
    assert [run.algorithm for run in algorithms.runs] == ["native:buffer"] * 3


def test_a_cancelled_batch_stops_between_items(world) -> None:
    from qgis_sdk.testing import FakeWorkers

    scope, layers, files, _ = world
    points = layers.open_vector(POINTS)
    workers = FakeWorkers()
    algorithms = FakeAlgorithms(
        FakeAlgorithmSetup(layers, scope, files=files, workers=workers)
    )
    algorithms.script_run("native:buffer", {"OUTPUT": POINTS})
    handle = algorithms.batch([native.Buffer(input=points.id) for _ in range(3)])

    assert handle.cancel() is True
    _drive(algorithms, workers)

    assert handle.status is JobStatus.CANCELLED
    assert list(algorithms.runs) == []
    with pytest.raises(QgisSdkJobCancelledError):
        _ = handle.result


def test_an_empty_batch_is_refused(world) -> None:
    *_, algorithms = world

    with pytest.raises(QgisSdkAlgorithmRejectedError) as refused:
        algorithms.batch([])

    assert "at least one" in "; ".join(refused.value.reasons)


def test_a_closed_scope_refuses_models_and_batches(world) -> None:
    scope, _, files, algorithms = world
    model = files.grant_file(MODEL)
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        algorithms.run_model(model, {})
    with pytest.raises(QgisSdkScopeClosedError):
        algorithms.batch([native.Buffer(input="any-layer")])
