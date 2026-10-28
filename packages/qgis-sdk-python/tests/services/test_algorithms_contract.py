"""Contract: an operation produces a new layer and never edits its source.

Runs against both backends, like the rest of this directory. Two things are
deliberately *not* asserted here because the in-memory double cannot know them:
whether a working CRS is projected, and whether its units are metres. Those need
a CRS database, so they are the native adapter's own tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import (
    AlgorithmRun,
    BufferRequest,
    CentroidRequest,
    FileRef,
    QgisSdkAlgorithmNotFoundError,
    QgisSdkAlgorithmRejectedError,
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


# -- the generic run (decision-64) -------------------------------------------


def test_the_registry_describes_the_core_buffer(services: Services) -> None:
    info = services.algorithms.describe("native:buffer")

    assert (info.id, info.provider, info.name) == ("native:buffer", "native", "buffer")
    assert [p.name for p in info.required] == ["INPUT"]
    assert info.parameter("DISTANCE").kind == "distance"
    assert info.parameter("OUTPUT").destination is True
    assert info.parameter("END_CAP_STYLE").options[:2] == ("Round", "Flat")
    assert [o.kind for o in info.outputs] == ["outputVector"]
    assert info in services.algorithms.list("native")
    assert info in services.algorithms.list()
    assert "native" in {p.id for p in services.algorithms.providers()}
    assert len(services.algorithms.list("native")) > 100


def test_an_unknown_algorithm_is_not_found(services: Services) -> None:
    with pytest.raises(QgisSdkAlgorithmNotFoundError) as error:
        services.algorithms.describe("saga:nothing")
    assert error.value.algorithm_id == "saga:nothing"
    with pytest.raises(QgisSdkAlgorithmNotFoundError):
        services.algorithms.run("saga:nothing", {})
    assert services.algorithms.list("saga") == ()


def test_a_run_is_validated_before_any_data_is_read(services: Services) -> None:
    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        services.algorithms.run("native:buffer", {"DISTANCE": "far", "EXTRA": 1})

    reasons = "; ".join(error.value.reasons)
    assert "INPUT is required" in reasons
    assert "DISTANCE must be a number" in reasons
    assert "EXTRA is not a parameter" in reasons
    assert services.layers.list_layers() == ()


def test_the_generic_run_produces_an_owned_vector_layer(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)

    result = services.algorithms.run(
        "native:buffer", {"INPUT": source.id, "DISTANCE": 0.01, "SEGMENTS": 4}
    )

    assert result.algorithm == "native:buffer"
    output = result.vector("OUTPUT")
    assert isinstance(output, VectorLayerInfo)
    assert output.id != source.id
    assert output.geometry_type == "polygon"
    assert set(source.field_names) <= set(output.field_names)
    assert services.layers.layer(source.id) == source
    assert services.project.layer_ids() == ()
    assert output.id in {layer.id for layer in services.layers.list_layers()}


def test_a_generated_request_class_runs_like_the_id(services: Services) -> None:
    from qgis_sdk.processing import native

    source = services.layers.open_vector(services.dataset)

    result = services.algorithms.run(native.Centroids(input=source.id))

    assert result.vector("OUTPUT").geometry_type == "point"
    with pytest.raises(QgisSdkAlgorithmRejectedError, match="params go with"):
        services.algorithms.run(native.Centroids(input=source.id), {"X": 1})


def test_scalar_and_file_outputs_come_back_typed(services: Services) -> None:
    source = services.layers.open_vector(services.dataset)

    result = services.algorithms.run(
        AlgorithmRun(
            "native:basicstatisticsforfields",
            {"INPUT_LAYER": source.id, "FIELD_NAME": "value"},
        )
    )

    assert result.value("COUNT") == 3
    report = result.file("OUTPUT_HTML_FILE")
    assert isinstance(report, FileRef)
    assert report.operations == ("read",)
    assert services.files is not None
    assert services.files.resolve(report).is_file()
    assert "OUTPUT_HTML_FILE" in set(result)


def test_an_explicit_output_cannot_replace_the_input_dataset(
    services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "input.geojson"
    source.write_bytes(services.dataset.read_bytes())
    register = getattr(services.layers, "register", None)
    if register is not None:
        register(
            source, name="input", geometry_type="point", field_names=("id", "value")
        )
    info = services.layers.open_vector(source)
    before = source.read_bytes()
    inode = source.stat().st_ino

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        services.algorithms.run(
            "native:centroids", {"INPUT": info.id, "OUTPUT": str(source)}
        )

    assert source.read_bytes() == before
    assert source.stat().st_ino == inode


@pytest.mark.parametrize("alias_kind", ["hardlink", "symlink", "unrelated"])
def test_an_explicit_existing_destination_is_preserved(
    services: Services, tmp_path: Path, alias_kind: str
) -> None:
    source = tmp_path / "input.geojson"
    source.write_bytes(services.dataset.read_bytes())
    register = getattr(services.layers, "register", None)
    if register is not None:
        register(
            source, name="input", geometry_type="point", field_names=("id", "value")
        )
    info = services.layers.open_vector(source)
    destination = tmp_path / "existing.geojson"
    if alias_kind == "hardlink":
        destination.hardlink_to(source)
    elif alias_kind == "symlink":
        try:
            destination.symlink_to(source)
        except (OSError, NotImplementedError) as error:
            pytest.skip(f"symbolic links unavailable: {error}")
    else:
        destination.write_text("unrelated user data", encoding="utf-8")
    source_before = source.read_bytes()
    output_before = destination.read_bytes()
    output_inode = destination.stat().st_ino

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        services.algorithms.run(
            "native:centroids", {"INPUT": info.id, "OUTPUT": str(destination)}
        )

    assert source.read_bytes() == source_before
    assert destination.read_bytes() == output_before
    assert destination.stat().st_ino == output_inode
    if alias_kind == "symlink":
        assert destination.is_symlink()


@pytest.mark.parametrize(
    "destination", ["memory:", "output.shp", "https://example.org/output.gpkg"]
)
def test_unverifiable_or_unsupported_explicit_destinations_are_refused(
    services: Services, destination: str
) -> None:
    source = services.layers.open_vector(services.dataset)
    with pytest.raises(QgisSdkAlgorithmRejectedError):
        services.algorithms.run(
            "native:centroids", {"INPUT": source.id, "OUTPUT": destination}
        )


def test_multiple_named_destinations_are_refused_before_writing(
    services: Services, tmp_path: Path
) -> None:
    source = services.layers.open_vector(services.dataset)
    first, second = tmp_path / "first.gpkg", tmp_path / "second.gpkg"

    with pytest.raises(QgisSdkAlgorithmRejectedError, match="at most one"):
        services.algorithms.run(
            "native:extractbyexpression",
            {
                "INPUT": source.id,
                "EXPRESSION": "1 = 1",
                "OUTPUT": str(first),
                "FAIL_OUTPUT": str(second),
            },
        )

    assert list(tmp_path.iterdir()) == []


def test_an_existing_file_ref_is_not_overwritten_even_with_a_write_grant(
    services: Services, tmp_path: Path
) -> None:
    source = services.layers.open_vector(services.dataset)
    destination = tmp_path / "existing.geojson"
    destination.write_text("user data", encoding="utf-8")
    assert services.files is not None
    ref = services.files.grant_file(destination, operations=("write",), overwrite=True)

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        services.algorithms.run("native:centroids", {"INPUT": source.id, "OUTPUT": ref})

    assert destination.read_text(encoding="utf-8") == "user data"


def test_an_unknown_layer_input_is_refused_by_the_generic_run(
    services: Services,
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        services.algorithms.run("native:buffer", {"INPUT": "no-such-layer"})
