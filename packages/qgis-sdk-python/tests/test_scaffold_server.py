"""``qgis-sdk new --host server``: a project QGIS Server can load.

Decision-52 splits one plugin project across three hosts, and the server one is
not a Desktop project with a different flag: QGIS Server never calls
``classFactory``, it imports the package and calls ``serverClassFactory``, so the
entry has to exist in the source tree and the starter has to declare hooks
instead of actions. The Desktop host stays exactly as it was, which is what the
last test here pins.

Everything in this file is pure: the generated project is inspected as text, run
in a bare interpreter, and checked by ``qgis-sdk check`` - no QGIS anywhere.
"""

from __future__ import annotations

import ast
import configparser
import subprocess
import sys
import tomllib
from pathlib import Path

import layers
import pytest
import qgis_sdk_tools.check.hosts as hosts_module
from qgis_sdk_tools.artifacts import introspect_plugin, render_metadata
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.project import require_project
from qgis_sdk_tools.scaffold import (
    GeneratedFile,
    QgisSdkScaffoldError,
    ScaffoldOptions,
    plan_scaffold,
    write_scaffold,
)


def ini_fields(text: str) -> dict[str, str]:
    """Read metadata.txt the way QGIS does, keeping its camelCase key names."""
    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    parser.read_string(text)
    return dict(parser["general"])


def content_of(plan: tuple[GeneratedFile, ...], path: str) -> str:
    return next(file.content for file in plan if file.path == path)


def server_options(**given: object) -> ScaffoldOptions:
    return ScaffoldOptions.resolve("demo_server", host="server", **given)  # type: ignore[arg-type]


def run_in_generated_project(
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


# -- the choice itself -------------------------------------------------------------


def test_the_desktop_host_is_what_a_project_gets_unless_it_asks() -> None:
    assert ScaffoldOptions.resolve("demo_tools").host == "desktop"
    assert server_options().host == "server"


@pytest.mark.parametrize(
    ("given", "named"),
    [
        pytest.param({"web": "vanilla"}, "--web", id="web"),
        pytest.param({"ui": "native"}, "--ui native", id="ui"),
        pytest.param({"algorithm": True}, "--algorithm", id="algorithm"),
    ],
)
def test_a_server_project_refuses_what_only_a_desktop_host_provides(
    given: dict[str, object], named: str
) -> None:
    """A request has no `iface` and no algorithm registry, so the flag is refused."""
    with pytest.raises(QgisSdkScaffoldError, match="needs the desktop host"):
        server_options(**given)
    assert named  # the message names the flag the caller used


def test_an_unknown_host_is_refused_by_name() -> None:
    with pytest.raises(QgisSdkScaffoldError, match="Invalid host 'app'"):
        ScaffoldOptions.resolve("demo_server", host="app")


# -- what the plan says ------------------------------------------------------------


def test_the_project_declares_the_server_host() -> None:
    plan = plan_scaffold(server_options())

    manifest = tomllib.loads(content_of(plan, "pyproject.toml"))
    assert manifest["tool"]["qgis-sdk"]["hosts"] == ["server"]
    assert manifest["tool"]["qgis-sdk"]["plugin"] == "demo_server.plugin:app"


def test_the_entry_point_is_the_factory_qgis_server_calls() -> None:
    """Empty ``__init__.py`` is the Desktop contract; a server project needs one."""
    entry = content_of(plan_scaffold(server_options()), "demo_server/__init__.py")

    assert "def serverClassFactory(serverIface):" in entry
    assert "QgsServerHost(HOOKS, serverIface).register()" in entry
    assert "HOOKS = ServerHooks((default_version, answer, everything_public))" in entry


def test_the_starter_declares_one_of_each_server_hook() -> None:
    plan = plan_scaffold(server_options())

    module = ast.parse(content_of(plan, "demo_server/plugin.py"))
    declared = {
        decorator.func.id  # type: ignore[union-attr]
        for function in module.body
        if isinstance(function, ast.FunctionDef)
        for decorator in function.decorator_list
        if isinstance(decorator, ast.Call)
    }
    assert declared == {"filter", "service", "access_control"}


def test_the_project_has_no_page_but_keeps_the_shared_scaffold() -> None:
    plan = plan_scaffold(server_options())

    paths = [file.path for file in plan]
    assert paths == [
        ".gitignore",
        "README.md",
        "demo_server/__init__.py",
        "demo_server/plugin.py",
        "pyproject.toml",
        "tests/test_plugin.py",
    ]
    readme = content_of(plan, "README.md")
    assert "WITH_SERVER=ON" in readme
    assert "conda-forge" in readme


def test_a_desktop_project_is_unchanged() -> None:
    """The server work is a branch, not a rewrite: Desktop keeps an empty entry."""
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    assert content_of(plan, "demo_tools/__init__.py") == ""
    manifest = tomllib.loads(content_of(plan, "pyproject.toml"))
    assert manifest["tool"]["qgis-sdk"]["hosts"] == ["desktop"]


# -- what the generated project does -----------------------------------------------


def test_the_generated_package_reaches_its_factory_without_qgis(tmp_path: Path) -> None:
    """Importing the package must not need ``qgis.server``; only registering does."""
    root = tmp_path / "demo_server"
    write_scaffold(server_options(), root)

    imported = run_in_generated_project(
        root,
        "import demo_server;"
        " assert callable(demo_server.serverClassFactory), demo_server;"
        " assert len(demo_server.HOOKS) == 3, demo_server.HOOKS",
    )

    assert imported.returncode == 0, imported.stderr


def test_the_starter_tests_pass_in_the_generated_project(tmp_path: Path) -> None:
    root = tmp_path / "demo_server"
    write_scaffold(server_options(), root)

    passed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": ":".join(map(str, layers.SOURCE_ROOTS)),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "NO_COLOR": "1",
        },
    )

    assert passed.returncode == 0, passed.stdout + passed.stderr


def test_check_accepts_the_generated_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server project declares the host it uses, so nothing is misdeclared."""
    monkeypatch.setattr(hosts_module, "qgis_server_state", lambda: None)
    root = tmp_path / "demo_server"
    write_scaffold(server_options(), root)

    report = check_project(root)

    rules = {diagnostic.rule for diagnostic in report.diagnostics}
    assert "HOST001" not in rules
    assert "HOST002" not in rules
    assert report.ok


# -- what ``build`` derives from the declaration -----------------------------------


def test_metadata_tells_qgis_server_to_load_the_plugin(tmp_path: Path) -> None:
    root = tmp_path / "demo_server"
    write_scaffold(server_options(), root)
    config = require_project(root)

    fields = ini_fields(render_metadata(config, introspect_plugin(config)))

    # QGIS Desktop ignores the key, so one ZIP serves both hosts.
    assert fields["server"] == "True"
    assert fields["name"] == "Demo Server"


def test_a_desktop_only_plugin_writes_no_server_key(tmp_path: Path) -> None:
    root = tmp_path / "demo_tools"
    write_scaffold(ScaffoldOptions.resolve("demo_tools"), root)
    config = require_project(root)

    fields = ini_fields(render_metadata(config, introspect_plugin(config)))

    assert "server" not in fields
