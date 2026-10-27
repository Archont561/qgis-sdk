"""The emitters turn a catalogue into importable Python and well-formed TypeScript.

Pure. The fixture catalogue is small but covers the awkward cases a real
registry has: a GRASS-style flag parameter (``-c``), a label that is not an
identifier, two algorithms with the same label, a multiple enum, a static
string enum, a provider id starting with a digit (``3d``), a kind the type
tables do not know, and a help string containing triple quotes.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import get_type_hints

import pytest
from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRun,
    Catalogue,
    OutputInfo,
    ParameterInfo,
    ProviderInfo,
    TypedRun,
)
from qgis_sdk.processing import codegen
from qgis_sdk.processing.codegen import (
    class_name,
    emit_python_module,
    emit_typescript_module,
    field_name,
    module_name,
    python_type,
    render_package,
    typescript_type,
)

BUFFER = AlgorithmInfo(
    id="native:buffer",
    provider="native",
    name="buffer",
    label="Buffer",
    group="Vector geometry",
    group_id="vectorgeometry",
    help='Computes a """buffer""" area.\nSecond paragraph.',
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
        ParameterInfo(name="OUTPUT", kind="sink", label="Buffered", extension="gpkg"),
    ),
    outputs=(OutputInfo(name="OUTPUT", kind="outputVector", label="Buffered"),),
)
STATS = AlgorithmInfo(
    id="qgis:basicstatisticsforfields",
    provider="qgis",
    name="basicstatisticsforfields",
    label="Basic statistics for fields",
    parameters=(
        ParameterInfo(name="INPUT_LAYER", kind="source"),
        ParameterInfo(name="FIELD_NAME", kind="field"),
        ParameterInfo(name="FIELDS", kind="field", multiple=True, optional=True),
        ParameterInfo(
            name="MODE", kind="enum", options=("a", "b"), multiple=True, default=[0]
        ),
        ParameterInfo(name="OUTPUT_HTML_FILE", kind="fileDestination", optional=True),
    ),
    outputs=(
        OutputInfo(name="COUNT", kind="outputNumber"),
        OutputInfo(name="OUTPUT_HTML_FILE", kind="outputHtml"),
        OutputInfo(name="ODD", kind="outputVariant"),
    ),
)
STATS_TWIN = AlgorithmInfo(
    id="qgis:basicstatistics2",
    provider="qgis",
    name="basicstatistics2",
    label="Basic statistics for fields",
    parameters=(ParameterInfo(name="class", kind="string"),),
)
GRASS = AlgorithmInfo(
    id="grass:r.buffer",
    provider="grass",
    name="r.buffer",
    label="r.buffer",
    parameters=(
        ParameterInfo(name="input", kind="raster"),
        ParameterInfo(name="-z", kind="boolean", default=False),
        ParameterInfo(name="2nd", kind="odd_custom_kind", optional=True),
        ParameterInfo(name="algorithm", kind="string", optional=True),
        ParameterInfo(name="output", kind="rasterDestination"),
    ),
    outputs=(OutputInfo(name="output", kind="outputRaster"),),
)
TESSELLATE = AlgorithmInfo(
    id="3d:tessellate",
    provider="3d",
    name="tessellate",
    label="Tessellate",
    parameters=(ParameterInfo(name="INPUT", kind="source"),),
)
CATALOGUE = Catalogue(
    qgis_version="4.2.3-Test",
    providers=(
        ProviderInfo(id="3d", label="QGIS (3D)"),
        ProviderInfo(id="grass", label="GRASS"),
        ProviderInfo(id="native", label="QGIS (native c++)"),
        ProviderInfo(id="qgis", label="QGIS"),
    ),
    algorithms=(TESSELLATE, GRASS, BUFFER, STATS, STATS_TWIN),
)


@pytest.mark.parametrize(
    ("name", "taken", "expected"),
    [
        ("END_CAP_STYLE", (), "end_cap_style"),
        ("input", (), "input"),
        ("-z", (), "flag_z"),
        ("2nd", (), "p_2nd"),
        ("class", (), "class_"),
        ("algorithm", (), "algorithm_"),
        ("params", (), "params_"),
        ("INPUT", ("input",), "input_"),
        ("DBSCAN*", (), "dbscan"),
        ("_private", (), "private"),
    ],
)
def test_field_names_are_identifiers_without_collisions(
    name: str, taken: tuple[str, ...], expected: str
) -> None:
    assert field_name(name, taken) == expected
    assert field_name(name, taken).isidentifier()


def test_class_names_come_from_labels_then_names_then_a_suffix() -> None:
    assert class_name(BUFFER) == "Buffer"
    assert class_name(STATS) == "BasicStatisticsForFields"
    assert class_name(STATS_TWIN, {"BasicStatisticsForFields"}) == "Basicstatistics2"
    assert (
        class_name(STATS_TWIN, {"BasicStatisticsForFields", "Basicstatistics2"})
        == "Basicstatistics22"
    )
    assert class_name(GRASS) == "RBuffer"
    assert module_name("3d") == "p3d"
    assert module_name("native") == "native"
    assert module_name("saga-next") == "saga_next"


def test_type_tables_fall_back_rather_than_fail() -> None:
    assert python_type(ParameterInfo(name="x", kind="odd_custom_kind")) == "object"
    assert typescript_type(ParameterInfo(name="x", kind="odd_custom_kind")) == "unknown"
    assert python_type(STATS.parameter("FIELDS")) == "list[str]"
    assert python_type(STATS.parameter("MODE")) == "list[int | str]"
    assert typescript_type(STATS.parameter("MODE")) == "(number | string)[]"
    assert python_type(BUFFER.parameter("OUTPUT")) == "Destination"
    assert typescript_type(BUFFER.parameter("INPUT")) == "LayerRef"
    # Every kind the sandbox registry reports is in both tables, or is one of
    # the deliberately untyped structured kinds.
    assert set(codegen.PYTHON_TYPES) == set(codegen.TYPESCRIPT_TYPES)


@pytest.fixture
def generated(tmp_path: Path) -> Path:
    package = tmp_path / "gen_processing"
    package.mkdir()
    for name, content in render_package(CATALOGUE).items():
        (package / name).write_text(content, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield package
    finally:
        sys.path.remove(str(tmp_path))
        for module in [m for m in sys.modules if m.startswith("gen_processing")]:
            del sys.modules[module]


def test_render_package_lists_every_file_and_restricts_the_catalogue() -> None:
    files = render_package(CATALOGUE, ["native", "3d"])

    assert set(files) == {"catalogue.json", "native.py", "p3d.py", "__init__.py"}
    restricted = Catalogue.from_json(files["catalogue.json"])
    assert [a.id for a in restricted.algorithms] == ["3d:tessellate", "native:buffer"]
    assert [p.id for p in restricted.providers] == ["3d", "native"]
    assert "__init__.py" not in render_package(CATALOGUE, ["native"], init=False)
    # Deterministic: the same catalogue renders byte-identical files.
    assert render_package(CATALOGUE) == render_package(CATALOGUE)


def test_generated_python_imports_and_builds_requests(generated: Path) -> None:
    package = importlib.import_module("gen_processing")
    native = importlib.import_module("gen_processing.native")
    qgis = importlib.import_module("gen_processing.qgis")
    grass = importlib.import_module("gen_processing.grass")
    p3d = importlib.import_module("gen_processing.p3d")

    assert package.QGIS_VERSION == "4.2.3-Test"
    assert package.PROVIDERS == ("3d", "grass", "native", "qgis")
    assert package.CATALOGUE.algorithm("native:buffer") == BUFFER
    assert native.PROVIDER == "native"
    assert native.ALGORITHM_IDS == ("native:buffer",)
    assert native.REGISTRY["native:buffer"] is native.Buffer
    assert issubclass(native.Buffer, TypedRun)

    request = native.Buffer(input="layer-1", distance=3, end_cap_style="Flat")
    assert request.params() == {
        "INPUT": "layer-1",
        "DISTANCE": 3,
        "END_CAP_STYLE": "Flat",
    }
    assert request.to_run() == AlgorithmRun(
        "native:buffer", {"INPUT": "layer-1", "DISTANCE": 3, "END_CAP_STYLE": "Flat"}
    )
    with pytest.raises(TypeError):
        native.Buffer("layer-1")  # keyword-only
    with pytest.raises(TypeError):
        native.Buffer(distance=3)  # a required input has no default
    assert "Computes a '''buffer''' area." in native.Buffer.__doc__
    assert "end_cap_style: End cap style" in native.Buffer.__doc__
    assert "one of: Round, Flat, Square" in native.Buffer.__doc__

    assert qgis.BasicStatisticsForFields.algorithm == "qgis:basicstatisticsforfields"
    assert qgis.Basicstatistics2(class_="x").params() == {"class": "x"}
    flags = grass.RBuffer(input="r", flag_z=True, algorithm_="a", p_2nd=1)
    assert flags.params() == {"input": "r", "-z": True, "algorithm": "a", "2nd": 1}
    assert flags.algorithm == "grass:r.buffer"
    assert p3d.Tessellate(input="l").algorithm == "3d:tessellate"


def test_generated_typeddicts_carry_qgis_names_and_requiredness(
    generated: Path,
) -> None:
    native = importlib.import_module("gen_processing.native")
    qgis = importlib.import_module("gen_processing.qgis")

    params = native.BufferParams
    assert params.__required_keys__ == {"INPUT"}
    assert params.__optional_keys__ == {
        "DISTANCE",
        "END_CAP_STYLE",
        "DISSOLVE",
        "OUTPUT",
    }
    hints = get_type_hints(params)
    assert hints["DISSOLVE"] is bool
    assert get_type_hints(native.BufferResult).keys() == {"OUTPUT"}
    assert set(qgis.BasicStatisticsForFieldsResult.__optional_keys__) == {
        "COUNT",
        "OUTPUT_HTML_FILE",
        "ODD",
    }
    # Fields of a request class: required first, then the rest defaulting to None.
    import dataclasses

    names = [f.name for f in dataclasses.fields(native.Buffer)]
    assert names == ["input", "distance", "end_cap_style", "dissolve", "output"]
    assert dataclasses.fields(native.Buffer)[1].default is None


def test_generated_python_passes_the_source_checks(generated: Path) -> None:
    import ast

    for path in generated.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert "Do not edit" in ast.get_docstring(tree)
        # A generated module may import only from the runtime's pure surface.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module.split(".")[0] in {
                    "__future__",
                    "dataclasses",
                    "typing",
                    "pathlib",
                    "qgis_sdk",
                }, node.module
                assert not node.module.startswith("qgis_sdk.adapters")


def test_typescript_module_declares_params_results_and_the_registry() -> None:
    text = emit_typescript_module(CATALOGUE, package="qgis-sdk")

    assert text.startswith(
        "// Generated by qgis-sdk processing generate from QGIS 4.2.3-Test."
    )
    assert 'from "qgis-sdk";' in text
    assert "export interface NativeBufferParams {" in text
    assert "\tINPUT: LayerRef;" in text
    assert "\tDISTANCE?: number;" in text
    assert "\tEND_CAP_STYLE?: number | string;" in text
    assert "\tOUTPUT?: Destination;" in text
    assert (
        "export interface NativeBufferResult {\n\tOUTPUT?: VectorLayerInfo;\n}" in text
    )
    assert "export interface QgisBasicStatisticsForFieldsParams {" in text
    assert "\tFIELDS?: string[];" in text
    assert "\tMODE?: (number | string)[];" in text
    assert "export interface QgisBasicstatistics2Params {" in text
    assert "export interface GrassRBufferParams {" in text
    assert '\t"-z"?: boolean;' in text
    assert '\t"2nd"?: unknown;' in text
    assert "export interface P3dTessellateParams {" in text
    assert "\tODD?: unknown;" in text
    assert (
        '\t"native:buffer": { params: NativeBufferParams; result: NativeBufferResult };'
        in text
    )
    assert (
        'export const PROVIDERS = ["3d", "grass", "native", "qgis"] as const;' in text
    )
    assert "export type AlgorithmId = keyof AlgorithmRegistry;" in text
    assert "/** End cap style — one of: Round, Flat, Square */" in text
    # The bound runner: the bridge's generic one with this registry filled in.
    assert "\trunAlgorithm as runAny," in text
    assert "export function runAlgorithm<K extends AlgorithmId>(" in text
    assert "\treturn runAny<AlgorithmRegistry, K>(qgis, id, params, options);" in text

    only_native = emit_typescript_module(CATALOGUE, ["native"])
    assert "GrassRBuffer" not in only_native
    assert 'from "@archont561/qgis-sdk";' in only_native
    assert only_native == emit_typescript_module(CATALOGUE, ["native"])


def test_python_module_of_a_provider_without_algorithms_is_still_valid() -> None:
    text = emit_python_module(CATALOGUE, "missing")

    compile(text, "missing.py", "exec")
    assert "REGISTRY: dict[str, type[TypedRun]] = {\n}" in text
