"""``qgis-sdk processing generate``: QGIS in a subprocess, pure emitters, drift check.

The reader runs in the project's QGIS install; here a fake process runner
plays it and writes the catalogue the subprocess would, so the command's
wiring - where it writes, what ``--check`` says, how a missing QGIS or a
failing reader is reported - is proven without QGIS.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from qgis_sdk.models import (
    AlgorithmInfo,
    Catalogue,
    OutputInfo,
    ParameterInfo,
    ProviderInfo,
)
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.processing import READER_MODULE
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from test_devtools_installs import make_prefix
from typer.testing import CliRunner

runner = CliRunner()

CATALOGUE = Catalogue(
    qgis_version="4.2.3-Test",
    providers=(
        ProviderInfo(id="native", label="QGIS"),
        ProviderInfo(id="saga", label="SAGA"),
    ),
    algorithms=(
        AlgorithmInfo(
            id="native:buffer",
            provider="native",
            name="buffer",
            label="Buffer",
            parameters=(
                ParameterInfo(name="INPUT", kind="source"),
                ParameterInfo(name="DISTANCE", kind="distance", default=10),
                ParameterInfo(name="OUTPUT", kind="sink"),
            ),
            outputs=(OutputInfo(name="OUTPUT", kind="outputVector"),),
        ),
        AlgorithmInfo(
            id="saga:slope",
            provider="saga",
            name="slope",
            label="Slope",
            parameters=(
                ParameterInfo(name="ELEVATION", kind="raster"),
                ParameterInfo(name="SLOPE", kind="rasterDestination"),
            ),
            outputs=(OutputInfo(name="SLOPE", kind="outputRaster"),),
        ),
    ),
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools", web="vanilla"), root)
    return root


def _reader(catalogue: Catalogue = CATALOGUE):
    """A process runner that behaves like the QGIS subprocess: writes --out."""

    def run(argv: Sequence[str], cwd: Path) -> int:
        out = Path(argv[argv.index("--out") + 1])
        providers = [argv[i + 1] for i, a in enumerate(argv) if a == "--provider"]
        written = catalogue
        if providers:
            written = Catalogue(
                qgis_version=catalogue.qgis_version,
                providers=tuple(p for p in catalogue.providers if p.id in providers),
                algorithms=tuple(
                    a for a in catalogue.algorithms if a.provider in providers
                ),
            )
        out.write_text(written.to_json(), encoding="utf-8")
        return 0

    return run


def _runtime(project: Path, prefix: Path, **kwargs) -> FakeCliRuntime:
    return FakeCliRuntime(
        project, {"QGIS_PREFIX_PATH": str(prefix), "PATH": ""}, **kwargs
    )


def test_generate_runs_the_reader_in_the_qgis_install_and_writes_both_sides(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path)
    runtime = _runtime(project, prefix, run_process=_reader())

    result = runner.invoke(app, ["processing", "generate"], obj=runtime)

    assert result.exit_code == 0, result.output + runtime.stderr
    ((argv, cwd),) = runtime.processes
    assert argv[:3] == (str(prefix / "bin" / "python"), "-m", READER_MODULE)
    assert "--out" in argv and "--provider" not in argv
    assert cwd == project
    env = runtime.environments[0]
    assert env["QGIS_PREFIX_PATH"] == str(prefix)
    assert str(prefix / "share" / "qgis" / "python") in env["PYTHONPATH"]
    assert "qgis_sdk" not in argv[0]
    package = project / "field_tools" / "processing"
    assert sorted(p.name for p in package.iterdir()) == [
        "__init__.py",
        "catalogue.json",
        "native.py",
        "saga.py",
    ]
    assert Catalogue.from_json((package / "catalogue.json").read_text()) == CATALOGUE
    assert "class Slope(TypedRun):" in (package / "saga.py").read_text()
    web = project / "web" / "src" / "processing.schema.ts"
    assert "export interface SagaSlopeParams {" in web.read_text()
    assert (
        '"saga:slope": { params: SagaSlopeParams; result: SagaSlopeResult };'
        in web.read_text()
    )
    assert "2 algorithms from 2 providers; 5 of 5 files changed" in result.output
    assert "reading the Processing registry of" in runtime.stderr


def test_provider_filters_restrict_the_reader_and_the_outputs(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path)
    runtime = _runtime(project, prefix, run_process=_reader())

    result = runner.invoke(
        app, ["processing", "generate", "--provider", "saga", "--no-web"], obj=runtime
    )

    assert result.exit_code == 0, result.output + runtime.stderr
    argv = runtime.processes[0][0]
    assert argv[-2:] == ("--provider", "saga")
    package = project / "field_tools" / "processing"
    assert sorted(p.name for p in package.iterdir()) == [
        "__init__.py",
        "catalogue.json",
        "saga.py",
    ]
    # The scaffold's own module (from the runtime snapshot) is left as it was.
    web = project / "web" / "src" / "processing.schema.ts"
    assert "SagaSlope" not in web.read_text()
    text = (package / "__init__.py").read_text()
    assert 'PROVIDERS: tuple[str, ...] = ("saga", )' in text


def test_check_reports_missing_and_stale_files_without_writing(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path)
    runtime = _runtime(project, prefix, run_process=_reader())

    missing = runner.invoke(app, ["processing", "generate", "--check"], obj=runtime)
    assert missing.exit_code == 1
    assert "catalogue.json does not exist" in runtime.stderr
    assert not (project / "field_tools" / "processing").exists()

    runtime = _runtime(project, prefix, run_process=_reader())
    assert runner.invoke(app, ["processing", "generate"], obj=runtime).exit_code == 0
    runtime = _runtime(project, prefix, run_process=_reader())
    current = runner.invoke(app, ["processing", "generate", "--check"], obj=runtime)
    assert current.exit_code == 0, runtime.stderr
    assert "5 generated files are up to date" in current.output

    stale = project / "web" / "src" / "processing.schema.ts"
    stale.write_text(stale.read_text() + "// edited\n")
    runtime = _runtime(project, prefix, run_process=_reader())
    drift = runner.invoke(app, ["processing", "generate", "--check"], obj=runtime)
    assert drift.exit_code == 1
    assert "processing.schema.ts is out of date" in runtime.stderr
    assert stale.read_text().endswith("// edited\n")


def test_a_catalogue_file_skips_the_subprocess_and_explicit_outs_win(
    project: Path, tmp_path: Path
) -> None:
    catalogue = tmp_path / "cat.json"
    catalogue.write_text(CATALOGUE.to_json())
    runtime = FakeCliRuntime(project)

    result = runner.invoke(
        app,
        [
            "processing",
            "generate",
            "--catalogue",
            str(catalogue),
            "--out",
            "field_tools/algos",
            "--web-out",
            "web/src/algos.ts",
        ],
        obj=runtime,
    )

    assert result.exit_code == 0, result.output + runtime.stderr
    assert runtime.processes == []
    assert (project / "field_tools" / "algos" / "native.py").exists()
    assert (project / "web" / "src" / "algos.ts").exists()


def test_an_unknown_provider_is_refused_with_what_the_host_has(
    project: Path, tmp_path: Path
) -> None:
    catalogue = tmp_path / "cat.json"
    catalogue.write_text(CATALOGUE.to_json())
    runtime = FakeCliRuntime(project)

    result = runner.invoke(
        app,
        [
            "processing",
            "generate",
            "--catalogue",
            str(catalogue),
            "--provider",
            "grass",
        ],
        obj=runtime,
    )

    assert result.exit_code == 2
    assert "no provider grass; it holds native, saga" in runtime.stderr


def test_a_failing_reader_and_a_missing_qgis_are_reported(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path)
    runtime = _runtime(project, prefix, run_process=lambda argv, cwd: 3)
    failed = runner.invoke(app, ["processing", "generate"], obj=runtime)
    assert failed.exit_code == 2
    assert "exit code 3" in runtime.stderr

    runtime = FakeCliRuntime(project, {"PATH": ""})
    absent = runner.invoke(
        app,
        ["processing", "generate", "--qgis-prefix", str(tmp_path / "nothing")],
        obj=runtime,
    )
    assert absent.exit_code == 2
    assert "nothing" in runtime.stderr
    assert runtime.processes == []


def test_generate_outside_a_project_needs_an_out(tmp_path: Path) -> None:
    catalogue = tmp_path / "cat.json"
    catalogue.write_text(CATALOGUE.to_json())
    runtime = FakeCliRuntime(tmp_path)

    result = runner.invoke(
        app, ["processing", "generate", "--catalogue", str(catalogue)], obj=runtime
    )

    assert result.exit_code == 2
    assert "nothing to write" in runtime.stderr


def test_the_generated_package_imports_from_the_project(
    project: Path, tmp_path: Path
) -> None:
    import subprocess
    import sys

    catalogue = tmp_path / "cat.json"
    catalogue.write_text(CATALOGUE.to_json())
    runtime = FakeCliRuntime(project)
    assert (
        runner.invoke(
            app,
            ["processing", "generate", "--catalogue", str(catalogue), "--no-web"],
            obj=runtime,
        ).exit_code
        == 0
    )

    script = (
        "from field_tools.processing import CATALOGUE, PROVIDERS\n"
        "from field_tools.processing import native, saga\n"
        "r = native.Buffer(input='l', distance=2)\n"
        "print(PROVIDERS, r.to_run().algorithm, sorted(r.params()), "
        "saga.Slope(elevation='dem').algorithm, len(CATALOGUE.algorithms))\n"
    )
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(project), *filter(None, [env.get("PYTHONPATH")])]
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        "('native', 'saga') native:buffer ['DISTANCE', 'INPUT'] saga:slope 2"
    )
    assert json.loads(
        (project / "field_tools" / "processing" / "catalogue.json").read_text()
    )
