"""The public scaffold contract: one validated plan, written without surprises.

Since decision-43 the plan is the author's project only: no ``metadata.txt``,
no ``classFactory`` and no view module. What QGIS needs is derived from
``pyproject.toml`` by ``build``/``dev`` (TASK-64), so the tests here pin that
derivation against the generated manifest instead of generated files.
"""

import ast
import configparser
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import layers
import pytest
from qgis_sdk_tools.artifacts import introspect_plugin, render_metadata
from qgis_sdk_tools.project import require_project
from qgis_sdk_tools.scaffold import (
    GeneratedFile,
    QgisSdkScaffoldError,
    ScaffoldOptions,
    plan_scaffold,
    write_scaffold,
)


def content_of(plan: tuple[GeneratedFile, ...], path: str) -> str:
    return next(file.content for file in plan if file.path == path)


def ini_fields(text: str) -> dict[str, str]:
    """Read metadata.txt the way QGIS does, keeping its camelCase key names."""
    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    parser.read_string(text)
    return dict(parser["general"])


def run_generated_project(
    project: Path, statement: str
) -> subprocess.CompletedProcess[str]:
    """Run one statement against the generated project in a bare interpreter."""
    script = f"import sys; sys.path[:0] = sys.argv[1:]; {statement}"
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(project),
            *map(str, layers.SOURCE_ROOTS),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_options_derive_a_visible_title_and_stable_defaults() -> None:
    options = ScaffoldOptions.resolve("demo_tools")

    assert options == ScaffoldOptions(
        plugin="demo_tools",
        title="Demo Tools",
        version="0.1.0",
        qgis_minimum_version="4.0",
        author="qgis-sdk scaffold user",
        email="someone@example.invalid",
    )


def test_options_trim_the_text_they_are_given() -> None:
    """Whitespace survives a shell command line, so it must not reach the plugin."""
    options = ScaffoldOptions.resolve(
        "demo_tools",
        title="  Field Tools  ",
        author="  Ana  ",
        email="  ana@example.invalid  ",
    )

    assert (options.title, options.author, options.email) == (
        "Field Tools",
        "Ana",
        "ana@example.invalid",
    )

    plan = plan_scaffold(options)
    manifest = tomllib.loads(content_of(plan, "pyproject.toml"))
    assert manifest["project"]["authors"] == [
        {"name": "Ana", "email": "ana@example.invalid"}
    ]
    assert manifest["project"]["description"].startswith("Field Tools:")
    assert '@plugin(id="demo_tools", title="Field Tools")' in content_of(
        plan, "demo_tools/plugin.py"
    )


@pytest.mark.parametrize("blank", ["", "   ", "\t"], ids=["empty", "spaces", "tab"])
@pytest.mark.parametrize("field", ["title", "author", "email"])
def test_options_reject_text_that_is_only_whitespace(field: str, blank: str) -> None:
    with pytest.raises(QgisSdkScaffoldError, match="non-empty"):
        ScaffoldOptions.resolve("demo_tools", **{field: blank})


@pytest.mark.parametrize(
    "plugin",
    ["Demo", "1plugin", "demo-tools", "qgis", "qgis_sdk", "os", "sys", ""],
)
def test_options_reject_a_package_name_qgis_or_python_already_own(plugin: str) -> None:
    with pytest.raises(QgisSdkScaffoldError) as error:
        ScaffoldOptions.resolve(plugin)

    assert "package name" in str(error.value)


def test_options_reject_a_blank_or_unsafe_version() -> None:
    with pytest.raises(QgisSdkScaffoldError):
        ScaffoldOptions.resolve("demo", version="nightly")


def test_plan_is_deterministic_and_lists_the_minimal_project_layout() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    assert [file.path for file in plan] == [
        ".gitignore",
        "README.md",
        "demo_tools/__init__.py",
        "demo_tools/plugin.py",
        "pyproject.toml",
        "tests/test_plugin.py",
    ]


def test_the_manifest_declares_the_plugin_class_and_qgis_facts() -> None:
    plan = plan_scaffold(
        ScaffoldOptions.resolve(
            "demo_tools", author="Ada", email="ada@example.test", version="1.2.3"
        )
    )

    manifest = tomllib.loads(content_of(plan, "pyproject.toml"))

    assert manifest["project"]["name"] == "demo-tools"
    assert manifest["project"]["version"] == "1.2.3"
    assert manifest["project"]["dependencies"] == ["qgis-sdk-runtime>=0.5,<0.6"]
    assert manifest["dependency-groups"] == {"dev": ["qgis-sdk-tools>=0.5,<0.6"]}
    assert manifest["tool"]["qgis-sdk"] == {
        "plugin": "demo_tools.plugin:DemoToolsPlugin",
        "qgis-minimum-version": "4.0",
        "experimental": True,
    }
    assert manifest["tool"]["pytest"]["ini_options"]["addopts"] == (
        "-p qgis_sdk_tools.pytest_plugin"
    )


def test_metadata_rendered_from_the_manifest_carries_the_fields_qgis_reads(
    tmp_path: Path,
) -> None:
    """The ZIP's metadata.txt is derived, so the derivation is what the plan pins."""
    project = tmp_path / "project"
    write_scaffold(
        ScaffoldOptions.resolve(
            "demo_tools", author="Ada", email="ada@example.test", version="1.2.3"
        ),
        project,
    )
    config = require_project(project)

    fields = ini_fields(render_metadata(config, introspect_plugin(config)))

    assert set(fields) == {
        "about",
        "author",
        "description",
        "email",
        "experimental",
        "hasProcessingProvider",
        "name",
        "qgisMinimumVersion",
        "version",
    }
    assert fields["name"] == "Demo Tools"
    assert fields["version"] == "1.2.3"
    assert fields["qgisMinimumVersion"] == "4.0"
    assert fields["author"] == "Ada"
    assert fields["email"] == "ada@example.test"
    assert fields["hasProcessingProvider"] == "no"
    assert not (project / "demo_tools" / "metadata.txt").exists()


def test_the_package_init_is_empty_because_build_appends_the_entry_point() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    assert content_of(plan, "demo_tools/__init__.py") == ""
    assert "classFactory" not in content_of(plan, "demo_tools/plugin.py")


def test_generated_python_is_parsable_and_uses_the_sdk_framework_explicitly() -> None:
    module = content_of(
        plan_scaffold(ScaffoldOptions.resolve("demo_tools")), "demo_tools/plugin.py"
    )

    ast.parse(module)
    assert "@plugin(id=" in module
    assert "@action(id=" in module
    assert "ctx: PluginContext" in module
    assert "import qgis" not in module


def test_readme_names_both_modes_and_their_one_real_difference() -> None:
    readme = content_of(
        plan_scaffold(ScaffoldOptions.resolve("demo_tools")), "README.md"
    )

    assert "Desktop mode" in readme
    assert "Standalone Qt mode" in readme
    assert "QgisSdkUnsupportedCapabilityError" in readme
    assert "no `iface`" in readme


def test_the_generated_project_runs_in_a_bare_interpreter_without_qgis(
    tmp_path: Path,
) -> None:
    """AC1's real claim: the entry point is importable and drives the lifecycle."""
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools"), project)

    result = run_generated_project(
        project,
        "from qgis_sdk.adapters.desktop import host;"
        "plugin = host('demo_tools.plugin:DemoToolsPlugin')(None);"
        "plugin.initGui();"
        "print(plugin.runtime.state.value);"
        "print(plugin.runtime.actions['ping'](7));"
        "plugin.unload(); plugin.unload();"
        "print(plugin.runtime.state.value)",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["running", "7", "stopped"]


def test_instantiating_the_generated_project_loads_no_native_module(
    tmp_path: Path,
) -> None:
    """Building the adapter is the whole QGIS-side contract, and it stays pure."""
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools"), project)

    result = run_generated_project(
        project,
        "import sys;"
        "from qgis_sdk.adapters.desktop import host;"
        "host('demo_tools.plugin:DemoToolsPlugin')(None);"
        "print('qgis' in sys.modules, 'PyQt6' in sys.modules)",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"


def test_the_starter_tests_pass_in_a_bare_interpreter(tmp_path: Path) -> None:
    """The scaffold's own tests are the first thing an author runs."""
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools"), project)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        # The parent's environment stays (Windows needs SYSTEMROOT to start
        # Python at all); only the SDK sources are put in front.
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(map(str, layers.SOURCE_ROOTS)),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout


def test_no_generated_python_file_names_a_native_import() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    for file in plan:
        if not file.path.endswith(".py"):
            continue
        modules = {
            alias.name
            for node in ast.walk(ast.parse(file.content))
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        native = {name for name in modules if name.split(".")[0] in {"qgis", "PyQt6"}}
        assert native == set(), f"{file.path}: {native}"


def test_every_generated_file_ends_with_exactly_one_newline() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    assert plan
    for file in plan:
        if file.content == "":  # the package marker, appended to by `build`
            continue
        assert file.content.endswith("\n"), file.path
        assert not file.content.endswith("\n\n"), file.path
        assert "\r" not in file.content, file.path


def test_write_lays_the_plan_on_disk_and_returns_the_written_paths(
    tmp_path: Path,
) -> None:
    options = ScaffoldOptions.resolve("demo_tools")

    written = write_scaffold(options, tmp_path / "project")

    plan = plan_scaffold(options)
    assert written == tuple(tmp_path / "project" / file.path for file in plan)
    assert all(path.is_file() for path in written)


def test_write_refuses_to_touch_an_existing_file_without_force(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools"), target)
    (target / "README.md").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(QgisSdkScaffoldError) as error:
        write_scaffold(ScaffoldOptions.resolve("demo_tools"), target)

    assert "README.md" in str(error.value)
    assert (target / "README.md").read_text(encoding="utf-8") == "keep me\n"


def test_force_rewrites_the_whole_plan(tmp_path: Path) -> None:
    target = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools"), target)
    (target / "README.md").write_text("stale\n", encoding="utf-8")

    write_scaffold(ScaffoldOptions.resolve("demo_tools"), target, force=True)

    assert "Desktop mode" in (target / "README.md").read_text(encoding="utf-8")


def test_a_missing_target_directory_is_created(tmp_path: Path) -> None:
    written = write_scaffold(
        ScaffoldOptions.resolve("demo_tools"), tmp_path / "deep" / "nested"
    )

    assert len(written) == 6
    assert all(path.is_file() for path in written)
