"""The reference plugin is the scaffold plus the plugin's own code (decision-41, -43).

``examples/simple`` is what ``qgis-sdk new`` writes plus the plugin's own code.
Its ``web/package.json`` must stay the scaffold's too - the same scripts and the
same pinned tooling - differing in one value only: the bridge it depends on is
this repository's ``packages/qgis-sdk-typescript`` through the Bun workspace,
not the release the scaffold pins for users. On the Python side the project
shape is the scaffold's as well: the same ``pyproject.toml`` tables, the same
SDK dependency windows, none of the host artifacts the scaffold stopped
writing. The end-to-end half of this contract lives in
``test_reference_example_native.py``.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tomllib

import layers
from qgis_sdk.server import ServerRequest
from qgis_sdk.testing import FakeServerInterface
from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold
from qgis_sdk_tools.scaffold.generate import sdk_requirements
from qgis_sdk_tools.scaffold.web import SDK_NPM_PACKAGE, UI_NPM_PACKAGE

EXAMPLE = layers.REPOSITORY_ROOT / "examples" / "simple"
SERVER_VARIANT = layers.REPOSITORY_ROOT / "examples" / "server"
WORKSPACE = "workspace:*"
HOST_ARTIFACTS = ("metadata.txt", "webview.py")


def _example_plan():
    return plan_scaffold(
        ScaffoldOptions.resolve(
            "simple",
            title="Simple",
            web="vanilla",
            placement="dock",
            package_manager="bun",
            sdk_dependency=WORKSPACE,
            ui_dependency=WORKSPACE,
        )
    )


def test_the_example_project_has_the_scaffold_shape_and_no_host_artifact() -> None:
    """decision-43: the project holds the plugin; build and dev render the rest."""
    scaffolded = tomllib.loads(
        next(f.content for f in _example_plan() if f.path == "pyproject.toml")
    )
    example = tomllib.loads((EXAMPLE / "pyproject.toml").read_text())

    assert set(example) == set(scaffolded)  # the same top-level tables
    assert set(example["tool"]) == set(scaffolded["tool"])
    assert example["tool"]["qgis-sdk"]["plugin"] == "simple.plugin:app"
    assert example["tool"]["qgis-sdk"]["web"] == scaffolded["tool"]["qgis-sdk"]["web"]
    assert example["tool"]["pytest"] == scaffolded["tool"]["pytest"]
    for name in HOST_ARTIFACTS:
        assert not (EXAMPLE / "simple" / name).exists(), name
    package_init = (EXAMPLE / "simple" / "__init__.py").read_text()
    assert "classFactory" not in package_init
    gitignore = (EXAMPLE / ".gitignore").read_text()
    assert ".qgis-sdk/" in gitignore and "dist/" in gitignore


def test_the_example_declares_the_windows_the_scaffold_writes() -> None:
    """``release.py stamp`` moves these with the kit; the scaffold derives them."""
    runtime_line, tools_line = sdk_requirements()
    example = tomllib.loads((EXAMPLE / "pyproject.toml").read_text())

    assert example["project"]["dependencies"] == [runtime_line]
    assert example["dependency-groups"] == {"dev": [tools_line]}


def test_the_example_page_is_the_scaffold_on_the_workspace_bridge() -> None:
    scaffolded = next(
        f.content for f in _example_plan() if f.path == "web/package.json"
    )

    example = json.loads((EXAMPLE / "web" / "package.json").read_text())
    assert example["dependencies"][SDK_NPM_PACKAGE] == WORKSPACE
    assert example["dependencies"][UI_NPM_PACKAGE] == WORKSPACE
    assert example == json.loads(scaffolded)


def test_the_example_page_is_a_member_of_the_bun_workspace() -> None:
    root = json.loads((layers.REPOSITORY_ROOT / "package.json").read_text())

    assert "examples/*/web" in root["workspaces"]
    assert not (EXAMPLE / "web" / "bun.lock").exists()  # the root lockfile owns it


# -- the app host: the same declaration, a second host ------------------------------


APP_PROBE = """
import json

from qgis_sdk.app import AppSession
from qgis_sdk.testing import FakeAppBackend

from simple.plugin import app

backend = FakeAppBackend()
session = AppSession(app, backend=backend, gui=False, grace=0.5)
session.start()
actions = sorted(session.runtime.actions)
report = session.stop()
print(json.dumps({
    "calls": backend.calls,
    "host": backend.surface.context.host.value,
    "actions": actions,
    "exits": backend.exits,
    "report": report.to_json(),
}))
"""


def test_the_example_declares_both_hosts() -> None:
    example = tomllib.loads((EXAMPLE / "pyproject.toml").read_text())

    assert example["tool"]["qgis-sdk"]["hosts"] == ["desktop", "app"]


def test_the_example_entry_is_the_runtime_main_with_the_same_declaration() -> None:
    entry = (EXAMPLE / "simple" / "__main__.py").read_text()
    example = tomllib.loads((EXAMPLE / "pyproject.toml").read_text())

    assert "from qgis_sdk.app import main as run_app" in entry
    assert "from .plugin import app" in entry
    assert "return run_app(app, argv)" in entry
    assert 'if __name__ == "__main__":' in entry
    # One declaration, two hosts: the entry starts what `plugin` names.
    assert example["tool"]["qgis-sdk"]["plugin"] == "simple.plugin:app"


def test_the_example_runs_headless_as_an_app_on_the_same_actions() -> None:
    """The bridge and the actions do not change with the host - only the host."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = layers.source_path(EXAMPLE)

    finished = subprocess.run(
        [sys.executable, "-c", APP_PROBE],
        capture_output=True,
        text=True,
        check=False,
        cwd=EXAMPLE,
        env=environment,
    )

    assert finished.returncode == 0, finished.stdout + finished.stderr
    found = json.loads(finished.stdout.strip().splitlines()[-1])
    assert found["host"] == "app"
    assert found["calls"] == ["init", "build", "exit"]
    assert found["exits"] == 1
    assert found["report"]["exited"] is True
    assert {"open_fixture", "selected_features", "buffer"} <= set(found["actions"])


# -- the server host: the reference example's third host ---------------------------


def _server_variant():
    """Import ``examples/server``'s package from its own directory, once."""
    source = str(SERVER_VARIANT)
    if source not in sys.path:
        sys.path.insert(0, source)
    return importlib.import_module("simple_server")


def test_the_server_variant_is_the_scaffold_shape_for_that_host() -> None:
    """``--host server`` writes the same tables; the plugin fills them in."""
    scaffolded = tomllib.loads(
        next(
            file.content
            for file in plan_scaffold(
                ScaffoldOptions.resolve(
                    "simple_server",
                    title="Simple server",
                    host="server",
                )
            )
            if file.path == "pyproject.toml"
        )
    )
    variant = tomllib.loads((SERVER_VARIANT / "pyproject.toml").read_text())

    assert set(variant) == set(scaffolded)
    assert set(variant["tool"]) == set(scaffolded["tool"])
    assert variant["tool"]["qgis-sdk"]["plugin"] == "simple_server.plugin:app"
    assert variant["tool"]["qgis-sdk"]["hosts"] == ["server"]
    assert "web" not in variant["tool"]["qgis-sdk"]


def test_the_server_variant_entry_is_the_factory_qgis_server_imports() -> None:
    """A server plugin keeps ``serverClassFactory`` in the source (decision-43)."""
    entry = (SERVER_VARIANT / "simple_server" / "__init__.py").read_text()

    assert "def serverClassFactory(serverIface):" in entry
    assert "classFactory = " not in entry
    # The adapter is imported inside the call, so the package imports without Qt.
    assert entry.count("from qgis_sdk.adapters.qgis.server import") == 1
    assert entry.index("from qgis_sdk.adapters.qgis.server import") > entry.index(
        "def serverClassFactory"
    )


def test_the_server_variant_answers_its_service_through_the_dispatcher() -> None:
    package = _server_variant()
    fixture = json.loads(
        (SERVER_VARIANT / "simple_server" / "data" / "points.geojson").read_text()
    )
    coordinates = [
        feature["geometry"]["coordinates"] for feature in fixture["features"]
    ]

    answered = FakeServerInterface().serve(
        package.HOOKS,
        ServerRequest(
            method="GET",
            url="http://localhost/qgis/qgis_mapserv.fcgi",
            params={"SERVICE": "SIMPLESERVER", "REQUEST": "extent"},
        ),
    )

    assert answered.status == 200
    assert json.loads(answered.body) == {
        "service": "SIMPLE_SERVER",
        # The filter filled the missing VERSION in before the service ran.
        "version": "1.0.0",
        "features": len(coordinates),
        "bbox": [
            min(point[0] for point in coordinates),
            min(point[1] for point in coordinates),
            max(point[0] for point in coordinates),
            max(point[1] for point in coordinates),
        ],
    }


def test_the_server_variant_refuses_a_private_layer() -> None:
    package = _server_variant()

    refused = FakeServerInterface().serve(
        package.HOOKS,
        ServerRequest(
            method="GET",
            url="http://localhost/qgis/qgis_mapserv.fcgi",
            params={
                "SERVICE": "SIMPLE_SERVER",
                "REQUEST": "extent",
                "LAYERS": "parcels,private_parcels",
            },
        ),
    )

    assert refused.status == 403
    assert "private_parcels" in refused.body.decode()
