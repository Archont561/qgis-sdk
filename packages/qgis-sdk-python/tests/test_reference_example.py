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

import json
import tomllib

import layers
from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold
from qgis_sdk_tools.scaffold.generate import sdk_requirements
from qgis_sdk_tools.scaffold.web import SDK_NPM_PACKAGE, UI_NPM_PACKAGE

EXAMPLE = layers.REPOSITORY_ROOT / "examples" / "simple"
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
