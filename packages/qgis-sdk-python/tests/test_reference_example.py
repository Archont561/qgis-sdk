"""The reference plugin's page is the scaffold's, on the workspace bridge (decision-41).

``examples/simple`` is what ``qgis-sdk new`` writes plus the plugin's own code.
Its ``web/package.json`` must stay the scaffold's too - the same scripts and the
same pinned tooling - differing in one value only: the bridge it depends on is
this repository's ``packages/qgis-sdk-typescript`` through the Bun workspace,
not the release the scaffold pins for users. The end-to-end half of this
contract lives in ``test_reference_example_native.py``.
"""

from __future__ import annotations

import json

import layers
from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold
from qgis_sdk_tools.scaffold.web import SDK_NPM_PACKAGE

EXAMPLE = layers.REPOSITORY_ROOT / "examples" / "simple"
WORKSPACE = "workspace:*"


def test_the_example_page_is_the_scaffold_on_the_workspace_bridge() -> None:
    plan = plan_scaffold(
        ScaffoldOptions.resolve(
            "simple",
            title="Simple",
            web="vanilla",
            placement="dock",
            package_manager="bun",
            sdk_dependency=WORKSPACE,
        )
    )
    scaffolded = next(f.content for f in plan if f.path == "web/package.json")

    example = json.loads((EXAMPLE / "web" / "package.json").read_text())
    assert example["dependencies"][SDK_NPM_PACKAGE] == WORKSPACE
    assert example == json.loads(scaffolded)


def test_the_example_page_is_a_member_of_the_bun_workspace() -> None:
    root = json.loads((layers.REPOSITORY_ROOT / "package.json").read_text())

    assert "examples/*/web" in root["workspaces"]
    assert not (EXAMPLE / "web" / "bun.lock").exists()  # the root lockfile owns it
