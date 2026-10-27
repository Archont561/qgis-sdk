"""The Processing catalogue models: plain data, JSON both ways, pure validation.

Nothing here imports QGIS. The catalogue is what the native reader produces
from ``QgsApplication.processingRegistry()`` and what the generator, the fake
and the bridge all consume (decision-64), so its shape and its validation
rules are proven once, here, over a hand-written catalogue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar

import pytest
from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRun,
    Catalogue,
    FileRef,
    OutputInfo,
    ParameterInfo,
    ProviderInfo,
    QgisSdkAlgorithmNotFoundError,
    QgisSdkAlgorithmRejectedError,
    RunResult,
    TypedRun,
    VectorLayerInfo,
    validate_parameters,
)

BUFFER = AlgorithmInfo(
    id="native:buffer",
    provider="native",
    name="buffer",
    label="Buffer",
    group="Vector geometry",
    group_id="vectorgeometry",
    help="Computes a buffer area.",
    parameters=(
        ParameterInfo(name="INPUT", kind="source", label="Input layer"),
        ParameterInfo(name="DISTANCE", kind="distance", label="Distance", default=10),
        ParameterInfo(
            name="END_CAP_STYLE",
            kind="enum",
            label="End cap style",
            default=0,
            options=("Round", "Flat", "Square"),
        ),
        ParameterInfo(name="DISSOLVE", kind="boolean", label="Dissolve", default=False),
        ParameterInfo(
            name="SEPARATE_DISJOINT",
            kind="boolean",
            label="Keep disjoint",
            default=False,
            advanced=True,
        ),
        ParameterInfo(
            name="OUTPUT",
            kind="sink",
            label="Buffered",
            destination=True,
            extension="gpkg",
        ),
    ),
    outputs=(OutputInfo(name="OUTPUT", kind="outputVector", label="Buffered"),),
)
STATS = AlgorithmInfo(
    id="qgis:basicstatisticsforfields",
    provider="qgis",
    name="basicstatisticsforfields",
    label="Basic statistics for fields",
    group="Vector analysis",
    group_id="vectoranalysis",
    help="",
    parameters=(
        ParameterInfo(name="INPUT_LAYER", kind="source", label="Input layer"),
        ParameterInfo(name="FIELD_NAME", kind="field", label="Field"),
        ParameterInfo(
            name="OUTPUT_HTML_FILE",
            kind="fileDestination",
            label="Statistics",
            destination=True,
            optional=True,
            extension="html",
        ),
    ),
    outputs=(
        OutputInfo(name="COUNT", kind="outputNumber", label="Count"),
        OutputInfo(name="OUTPUT_HTML_FILE", kind="outputHtml", label="Statistics"),
    ),
)
CATALOGUE = Catalogue(
    qgis_version="4.0.0",
    providers=(
        ProviderInfo(id="native", label="QGIS (native c++)"),
        ProviderInfo(id="qgis", label="QGIS"),
    ),
    algorithms=(BUFFER, STATS),
)


def test_catalogue_round_trips_through_json() -> None:
    text = CATALOGUE.to_json()

    rebuilt = Catalogue.from_json(text)

    assert rebuilt == CATALOGUE
    # Stable key order, so a regenerated snapshot diffs by content only.
    assert json.loads(text)["algorithms"][0]["id"] == "native:buffer"
    assert Catalogue.from_dict(json.loads(text)) == CATALOGUE


def test_catalogue_looks_up_algorithms_and_providers() -> None:
    assert CATALOGUE.algorithm("native:buffer") is BUFFER
    assert [a.id for a in CATALOGUE.by_provider("qgis")] == [STATS.id]
    assert [p.id for p in CATALOGUE.providers] == ["native", "qgis"]
    with pytest.raises(QgisSdkAlgorithmNotFoundError) as error:
        CATALOGUE.algorithm("saga:nothing")
    assert error.value.algorithm_id == "saga:nothing"
    assert error.value.code == "algorithm_not_found"


def test_algorithm_info_separates_inputs_from_destinations() -> None:
    assert [p.name for p in BUFFER.inputs] == [
        "INPUT",
        "DISTANCE",
        "END_CAP_STYLE",
        "DISSOLVE",
        "SEPARATE_DISJOINT",
    ]
    assert [p.name for p in BUFFER.destinations] == ["OUTPUT"]
    assert BUFFER.parameter("DISTANCE").default == 10
    assert BUFFER.parameter("MISSING") is None
    # Required means: not optional, no default, not a destination.
    assert [p.name for p in BUFFER.required] == ["INPUT"]
    assert [p.name for p in STATS.required] == ["INPUT_LAYER", "FIELD_NAME"]


def test_parameter_info_defaults_are_json_only() -> None:
    with pytest.raises(ValueError, match="JSON"):
        ParameterInfo(name="X", kind="number", default=object())  # type: ignore[arg-type]


def test_validate_parameters_refuses_every_problem_at_once() -> None:
    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        validate_parameters(
            BUFFER,
            {"DISTANCE": "far", "END_CAP_STYLE": 7, "DISSOLVE": "yes", "EXTRA": 1},
        )

    assert error.value.request == "native:buffer"
    reasons = "\n".join(error.value.reasons)
    assert "INPUT is required" in reasons
    assert "DISTANCE must be a number" in reasons
    assert "END_CAP_STYLE must be one of" in reasons
    assert "DISSOLVE must be a boolean" in reasons
    assert "EXTRA is not a parameter of native:buffer" in reasons
    # Values never appear in the reasons, so the error is loggable as-is.
    assert "far" not in reasons and "yes" not in reasons


def test_validate_parameters_accepts_the_shapes_qgis_accepts() -> None:
    validate_parameters(
        BUFFER,
        {
            "INPUT": "layer-1",
            "DISTANCE": 2,
            "END_CAP_STYLE": "Flat",
            "DISSOLVE": True,
            "OUTPUT": None,
        },
    )
    validate_parameters(
        STATS,
        {
            "INPUT_LAYER": FileRef(id="a" * 16, name="x", operations=("read",)),
            "FIELD_NAME": "value",
        },
    )
    # A destination left out is allocated by the backend; naming one is fine.
    validate_parameters(BUFFER, {"INPUT": "layer-1", "OUTPUT": "/tmp/out.gpkg"})
    # An optional parameter may be None explicitly.
    validate_parameters(
        STATS, {"INPUT_LAYER": "l", "FIELD_NAME": "f", "OUTPUT_HTML_FILE": None}
    )


def test_validate_parameters_refuses_none_for_a_required_input() -> None:
    with pytest.raises(QgisSdkAlgorithmRejectedError, match="INPUT is required"):
        validate_parameters(BUFFER, {"INPUT": None})


def test_algorithm_run_is_a_plain_request() -> None:
    run = AlgorithmRun("native:buffer", {"INPUT": "l", "DISTANCE": 5})

    assert run.algorithm == "native:buffer"
    assert run.params == {"INPUT": "l", "DISTANCE": 5}
    assert run.params is not None
    with pytest.raises(QgisSdkAlgorithmRejectedError, match="provider:name"):
        AlgorithmRun("buffer", {})
    with pytest.raises(QgisSdkAlgorithmRejectedError, match="strings"):
        AlgorithmRun("native:buffer", {1: "x"})  # type: ignore[dict-item]


def test_typed_run_maps_fields_back_to_qgis_names() -> None:
    # ``ClassVar`` must be visible at module level for a dataclass to honour a
    # string annotation (``from __future__ import annotations``); the generated
    # modules import it at the top for the same reason.
    @dataclass(frozen=True, slots=True)
    class Buffer(TypedRun):
        algorithm: ClassVar[str] = "native:buffer"
        _names: ClassVar[dict[str, str]] = {
            "input": "INPUT",
            "distance": "DISTANCE",
            "output": "OUTPUT",
        }
        input: str
        distance: float = 10
        output: str | None = None

    request = Buffer(input="layer-1", distance=3)

    assert request.params() == {"INPUT": "layer-1", "DISTANCE": 3}
    assert Buffer(input="l", output="out.gpkg").params()["OUTPUT"] == "out.gpkg"
    assert request.to_run() == AlgorithmRun(
        "native:buffer", {"INPUT": "layer-1", "DISTANCE": 3}
    )


def test_run_result_discriminates_outputs_on_the_wire() -> None:
    layer = VectorLayerInfo(
        id="out-1",
        name="buffer",
        geometry_type="polygon",
        field_names=("id",),
        crs="EPSG:3857",
    )
    ref = FileRef(id="b" * 16, name="stats.html", operations=("read",))
    result = RunResult(
        algorithm="qgis:basicstatisticsforfields",
        outputs={"OUTPUT": layer, "OUTPUT_HTML_FILE": ref, "COUNT": 3, "EMPTY": None},
    )

    assert result.vector("OUTPUT") is layer
    assert result.file("OUTPUT_HTML_FILE") is ref
    assert result.value("COUNT") == 3
    assert result["COUNT"] == 3
    assert set(result) == {"OUTPUT", "OUTPUT_HTML_FILE", "COUNT", "EMPTY"}
    with pytest.raises(KeyError):
        result.vector("COUNT")
    with pytest.raises(KeyError):
        result.file("OUTPUT")
    wire = result.to_wire()
    assert wire["algorithm"] == "qgis:basicstatisticsforfields"
    outputs = {entry["name"]: entry for entry in wire["outputs"]}
    assert outputs["OUTPUT"] == {
        "name": "OUTPUT",
        "kind": "vector",
        "layer": {
            "id": "out-1",
            "name": "buffer",
            "geometry_type": "polygon",
            "field_names": ["id"],
            "crs": "EPSG:3857",
        },
    }
    assert outputs["OUTPUT_HTML_FILE"] == {
        "name": "OUTPUT_HTML_FILE",
        "kind": "file",
        "file": ref.to_wire(),
    }
    assert outputs["COUNT"] == {"name": "COUNT", "kind": "value", "value": 3}
    assert outputs["EMPTY"] == {"name": "EMPTY", "kind": "value", "value": None}
    assert RunResult.from_wire(wire) == result
