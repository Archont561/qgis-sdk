"""Where a run allocates its outputs: the provider's name, made safe.

Nothing here imports QGIS. A backend that allocates the destinations a caller
left out writes into the run directory under a name the *provider* chose -
``OUTPUT`` for a registered algorithm, ``native:centroids_1:CENTROIDS`` for
the destination Processing derives for a model's child - so the translation
of that name into a file name is a pure rule, and the rule that keeps it
inside the run directory is proven here rather than in a native lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.models import (
    AlgorithmInfo,
    OutputInfo,
    ParameterInfo,
    QgisSdkAlgorithmRejectedError,
)
from qgis_sdk.processing.runs import destination_path, plan_destinations


def _a_model_that_exposes_facts1(names, renamed):
    assert names == {
        "native:centroids_1:CENTROIDS": "centroids",
        "native:basicstatisticsforfields_1:OUTPUT_HTML_FILE": "report",
    }
    kinds = {output.name: output.kind for output in renamed.outputs}
    assert kinds["centroids"] == "outputVector"
    # A file destination is a file, whatever it writes.
    assert kinds["report"] == "outputFile"


RUN = Path("/run/run-1")


def _destination(name: str, **changes: object) -> ParameterInfo:
    return ParameterInfo(name=name, kind="sink", destination=True, **changes)


def test_a_registered_algorithms_uppercase_name_is_lowered_and_suffixed() -> None:
    path = destination_path(RUN, _destination("OUTPUT", extension="gpkg"))

    assert path == RUN / "output.gpkg"


def test_a_models_child_destination_translates_instead_of_being_refused() -> None:
    # Processing names a model's derived destinations after the child and the
    # output it writes; a colon cannot reach a file name, so it is a
    # separator here, not a refusal.
    path = destination_path(
        RUN, _destination("native:centroids_1:CENTROIDS", extension="gpkg")
    )

    assert path == RUN / "native_centroids_1_centroids.gpkg"
    assert path.parent == RUN


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "C:\\Windows\\evil", "/absolute/path", "..", "...", "_"],
)
def test_no_provider_name_escapes_the_run_directory(name: str) -> None:
    with pytest.raises(ValueError, match="unsafe provider-defined name"):
        destination_path(RUN, _destination(name, extension="gpkg"))


@pytest.mark.parametrize("name", ["con", "PRN", "aux", "NUL", "com1", "lpt9"])
def test_a_windows_device_name_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="unsafe provider-defined name"):
        destination_path(RUN, _destination(name, extension="gpkg"))


@pytest.mark.parametrize("extension", ["a/b", "gp kg", "../x", "g" * 17])
def test_an_extension_outside_the_alphabet_is_refused(extension: str) -> None:
    with pytest.raises(ValueError, match="unsafe provider-defined name"):
        destination_path(RUN, _destination("OUTPUT", extension=extension))


def test_a_missing_extension_falls_back_to_the_kind() -> None:
    assert destination_path(RUN, _destination("OUTPUT")) == RUN / "output.gpkg"
    folder = ParameterInfo(name="Reports", kind="folderDestination", destination=True)
    assert destination_path(RUN, folder) == RUN / "reports"


def test_two_provider_names_that_translate_alike_are_refused_not_overwritten() -> None:
    info = AlgorithmInfo(
        id="model:report",
        provider="model",
        name="report",
        label="Report model",
        group="",
        group_id="",
        help="",
        parameters=(
            _destination("native:centroids_1:CENTROIDS"),
            _destination("native_centroids_1_centroids"),
        ),
        outputs=(OutputInfo(name="CENTROIDS", kind="outputVector", label="Centroids"),),
    )

    with pytest.raises(QgisSdkAlgorithmRejectedError) as refused:
        plan_destinations(info, {}, lambda ref: Path("/unreachable"))

    assert "collide" in str(refused.value)


def test_planning_allocates_one_name_per_omitted_destination() -> None:
    info = AlgorithmInfo(
        id="model:report",
        provider="model",
        name="report",
        label="Report model",
        group="",
        group_id="",
        help="",
        parameters=(
            _destination("native:centroids_1:CENTROIDS"),
            _destination("native:basicstatisticsforfields_1:OUTPUT_HTML_FILE"),
        ),
        outputs=(
            OutputInfo(name="CENTROIDS", kind="outputVector", label="Centroids"),
            OutputInfo(name="OUTPUT_HTML_FILE", kind="outputHtml", label="Report"),
        ),
    )

    assert plan_destinations(info, {}, lambda ref: Path("/unreachable")) == {}


def test_a_models_outputs_are_named_after_their_descriptions() -> None:
    from qgis_sdk.processing.runs import model_output_names

    info = AlgorithmInfo(
        id="model:report",
        provider="model",
        name="report",
        label="Report model",
        group="",
        group_id="",
        help="",
        parameters=(),
        outputs=(
            OutputInfo(name="CENTROIDS", kind="outputVector", label="Centroids"),
            OutputInfo(name="OUTPUT_HTML_FILE", kind="outputHtml", label="Report"),
        ),
    )

    renamed, names = model_output_names(info)

    assert [output.name for output in renamed.outputs] == ["centroids", "report"]
    assert names == {"CENTROIDS": "centroids", "OUTPUT_HTML_FILE": "report"}
    # The child's name is the key the run answers under; the model's is the
    # name the caller reads.
    assert renamed.outputs[0].kind == "outputVector"


def test_two_outputs_described_alike_keep_distinct_names() -> None:
    from qgis_sdk.processing.runs import model_output_names

    info = AlgorithmInfo(
        id="model:twins",
        provider="model",
        name="twins",
        label="Twins",
        group="",
        group_id="",
        help="",
        parameters=(),
        outputs=(
            OutputInfo(name="FIRST", kind="outputVector", label="Layer"),
            OutputInfo(name="SECOND", kind="outputVector", label="Layer"),
        ),
    )

    _, names = model_output_names(info)

    assert names == {"FIRST": "layer", "SECOND": "layer_2"}


def test_an_output_with_no_description_keeps_its_own_name() -> None:
    from qgis_sdk.processing.runs import model_output_names

    info = AlgorithmInfo(
        id="model:plain",
        provider="model",
        name="plain",
        label="Plain",
        group="",
        group_id="",
        help="",
        parameters=(),
        outputs=(OutputInfo(name="OUTPUT", kind="outputVector", label=""),),
    )

    _, names = model_output_names(info)

    assert names == {"OUTPUT": "output"}


def test_a_model_that_exposes_destinations_names_them_by_description() -> None:
    from qgis_sdk.processing.runs import model_output_names

    # The shape a loaded model answers with: no declared outputs, and one
    # destination parameter per child output, named after the child.
    info = AlgorithmInfo(
        id="model:report",
        provider="model",
        name="report",
        label="Report model",
        group="",
        group_id="",
        help="",
        parameters=(
            ParameterInfo(name="FEATS", kind="source", label="Features"),
            ParameterInfo(
                name="native:centroids_1:CENTROIDS",
                kind="sink",
                label="Centroids",
                destination=True,
                extension="gpkg",
            ),
            ParameterInfo(
                name="native:basicstatisticsforfields_1:OUTPUT_HTML_FILE",
                kind="fileDestination",
                label="Report",
                destination=True,
                extension="html",
            ),
        ),
        outputs=(),
    )

    renamed, names = model_output_names(info)

    _a_model_that_exposes_facts1(names, renamed)


def test_the_answer_is_matched_whatever_case_the_file_declares() -> None:
    from qgis_sdk.processing.runs import model_output_names

    info = AlgorithmInfo(
        id="model:report",
        provider="model",
        name="report",
        label="Report model",
        group="",
        group_id="",
        help="",
        parameters=(
            ParameterInfo(
                name="native:centroids_1:CENTROIDS",
                kind="sink",
                label="Centroids",
                destination=True,
                extension="gpkg",
            ),
        ),
        outputs=(),
    )

    _, names = model_output_names(info)

    answered = "native:centroids_1:centroids"
    assert {key.lower(): value for key, value in names.items()}[answered] == (
        "centroids"
    )


# The shape this Processing answers: destination parameters whose own
# descriptions are empty, and a model that still declares what each
# exposed output is.
def test_what_the_model_declares_decides_the_name() -> None:
    from qgis_sdk.processing.runs import model_output_names

    info = AlgorithmInfo(
        id="model:report",
        provider="model",
        name="report",
        label="Report model",
        group="",
        group_id="",
        help="",
        parameters=(
            ParameterInfo(
                name="native:basicstatisticsforfields_1:OUTPUT_HTML_FILE",
                kind="fileDestination",
                label="",
                destination=True,
                extension="html",
            ),
        ),
        outputs=(),
    )
    renamed, names = model_output_names(
        info,
        {"native:basicstatisticsforfields_1:OUTPUT_HTML_FILE": "Report"},
    )
    assert names == {"native:basicstatisticsforfields_1:OUTPUT_HTML_FILE": "report"}
    assert [output.name for output in renamed.outputs] == ["report"]


def test_the_model_document_says_what_each_output_is() -> None:
    from qgis_sdk.processing.runs import declared_model_outputs

    fixture = Path(__file__).parent / "fixtures" / "reference" / "report.model3"

    declared = declared_model_outputs(fixture)

    assert declared["native:centroids_1:CENTROIDS"] == "Centroids"
    assert declared["native:basicstatisticsforfields_1:OUTPUT_HTML_FILE"] == ("Report")
    assert declared["report"] == "Report"


def test_a_document_that_cannot_be_read_declares_nothing(tmp_path: Path) -> None:
    from qgis_sdk.processing.runs import declared_model_outputs

    broken = tmp_path / "broken.model3"
    broken.write_text("<!DOCTYPE model><Option", encoding="utf-8")

    assert declared_model_outputs(broken) == {}
    assert declared_model_outputs(tmp_path / "absent.model3") == {}
