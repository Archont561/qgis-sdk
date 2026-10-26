"""The web half of ``qgis-sdk new``: vanilla or React, dialog or dock (TASK-19)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import layers
import pytest
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.scaffold import (
    GeneratedFile,
    QgisSdkScaffoldError,
    ScaffoldOptions,
    WebOptions,
    plan_scaffold,
    write_scaffold,
)
from qgis_sdk_tools.scaffold.web import (
    BROWSER_TARGET,
    SDK_NPM_PACKAGE,
    SDK_NPM_VERSION,
    WEB_TEMPLATE_VERSIONS,
    install_command,
    script_command,
)

PLAIN_FILES = [
    ".gitignore",
    "README.md",
    "field_tools/__init__.py",
    "field_tools/metadata.txt",
    "field_tools/plugin.py",
    "pyproject.toml",
    "tests/test_plugin_smoke.py",
]
WEB_COMMON = [
    "field_tools/webview.py",
    "web/.gitignore",
    "web/index.html",
    "web/package.json",
    "web/src/bridge.ts",
    "web/src/transport.ts",
    "web/tsconfig.json",
    "web/vite.config.ts",
]
VANILLA_ONLY = ["web/src/app.test.ts", "web/src/app.ts", "web/src/main.ts"]
REACT_ONLY = ["web/src/App.test.tsx", "web/src/App.tsx", "web/src/main.tsx"]


def options(**web: str) -> ScaffoldOptions:
    return ScaffoldOptions.resolve("field_tools", **web)


def content_of(plan: tuple[GeneratedFile, ...], path: str) -> str:
    return next(file.content for file in plan if file.path == path)


# -- options -----------------------------------------------------------------


def test_a_plugin_without_a_page_has_no_web_options_and_the_old_plan() -> None:
    resolved = options()

    assert resolved.web is None
    assert [file.path for file in plan_scaffold(resolved)] == PLAIN_FILES


def test_the_web_choices_resolve_with_defaults_for_what_was_left_out() -> None:
    assert options(web="vanilla").web == WebOptions("vanilla", "dialog", "npm")
    assert options(
        web="react", placement="dock", package_manager="bun"
    ).web == WebOptions("react", "dock", "bun")


@pytest.mark.parametrize(
    ("given", "message"),
    [
        (
            {"web": "svelte"},
            "Invalid web framework 'svelte': choose one of vanilla, react",
        ),
        (
            {"web": "react", "placement": "panel"},
            "Invalid placement 'panel': choose one of dialog, dock",
        ),
        (
            {"web": "react", "package_manager": "yarn"},
            "Invalid package manager 'yarn': choose one of npm, pnpm, bun",
        ),
        ({"placement": "dock"}, "A placement needs a web framework"),
        ({"package_manager": "bun"}, "A package manager needs a web framework"),
        (
            {"sdk_dependency": "file:../pkg"},
            "A SDK dependency needs a web framework",
        ),
        (
            {"web": "vanilla", "sdk_dependency": "  "},
            "The SDK dependency must be a non-empty npm version or spec",
        ),
        (
            {"web": "vanilla", "sdk_dependency": "file: ../pkg"},
            "The SDK dependency must be a non-empty npm version or spec",
        ),
    ],
)
def test_an_invalid_or_orphaned_web_choice_is_refused(
    given: dict[str, str], message: str
) -> None:
    with pytest.raises(QgisSdkScaffoldError, match=message):
        options(**given)


@pytest.mark.parametrize("name", ["web", "tests"])
def test_a_package_named_like_a_project_directory_is_refused(name: str) -> None:
    with pytest.raises(QgisSdkScaffoldError, match="already owns"):
        ScaffoldOptions.resolve(name)


# -- the plan ----------------------------------------------------------------


def test_the_vanilla_plan_adds_the_web_app_and_the_view_module() -> None:
    paths = [file.path for file in plan_scaffold(options(web="vanilla"))]

    assert paths == sorted(PLAIN_FILES + WEB_COMMON + VANILLA_ONLY)


def test_the_react_plan_swaps_the_page_files_for_tsx() -> None:
    paths = [file.path for file in plan_scaffold(options(web="react"))]

    assert paths == sorted(PLAIN_FILES + WEB_COMMON + REACT_ONLY)


def test_the_plan_is_deterministic_per_choice() -> None:
    assert plan_scaffold(options(web="react", placement="dock")) == plan_scaffold(
        options(web="react", placement="dock")
    )
    assert plan_scaffold(options(web="react", placement="dock")) != plan_scaffold(
        options(web="react", placement="dialog")
    )


@pytest.mark.parametrize("framework", ["vanilla", "react"])
@pytest.mark.parametrize("manager", ["npm", "pnpm", "bun"])
def test_package_json_pins_the_sdk_exactly_and_keeps_vite_whatever_the_manager(
    framework: str, manager: str
) -> None:
    plan = plan_scaffold(options(web=framework, package_manager=manager))
    package = json.loads(content_of(plan, "web/package.json"))

    assert package["name"] == "field_tools-web"
    assert package["private"] is True
    assert package["type"] == "module"
    assert package["dependencies"][SDK_NPM_PACKAGE] == SDK_NPM_VERSION == "0.3.0"
    assert package["scripts"] == {
        "dev": "vite",
        "build": "vite build",
        "test": "vitest run",
        "typecheck": "tsc --noEmit",
        "bindings": "cd .. && qgis-sdk bridge generate --plugin field_tools.plugin:FieldToolsPlugin --out web/src/bridge.ts --check",
    }
    pinned = {**package["dependencies"], **package["devDependencies"]}
    for name, version in pinned.items():
        assert version[0].isdigit(), f"{name} is not pinned exactly: {version}"
        assert version == WEB_TEMPLATE_VERSIONS.get(name, SDK_NPM_VERSION)
    assert "vite" in package["devDependencies"]
    assert "vitest" in package["devDependencies"]
    assert "bunup" not in pinned  # library tooling, never an app's (decision-18)
    assert ("react" in package["dependencies"]) is (framework == "react")
    assert ("@vitejs/plugin-react" in package["devDependencies"]) is (
        framework == "react"
    )


def test_an_explicit_sdk_dependency_replaces_the_pin_and_nothing_else() -> None:
    """Inside this repository the page depends on the workspace bridge (decision-41)."""
    spec = "file:../../../packages/qgis-sdk-typescript"
    pinned = plan_scaffold(options(web="react", package_manager="bun"))
    workspace = plan_scaffold(
        options(web="react", package_manager="bun", sdk_dependency=spec)
    )

    package = json.loads(content_of(workspace, "web/package.json"))
    assert package["dependencies"][SDK_NPM_PACKAGE] == spec
    expected = json.loads(content_of(pinned, "web/package.json"))
    expected["dependencies"][SDK_NPM_PACKAGE] = spec
    assert package == expected
    others = [
        (file.path, file.content)
        for file in workspace
        if file.path != "web/package.json"
    ]
    assert others == [
        (file.path, file.content) for file in pinned if file.path != "web/package.json"
    ]
    assert options(web="vanilla").web is not None
    assert options(web="vanilla").web.sdk_dependency is None


def test_vite_targets_the_qualified_chromium_and_builds_into_the_plugin_package() -> (
    None
):
    plan = plan_scaffold(options(web="react"))
    config = content_of(plan, "web/vite.config.ts")

    assert 'base: "./"' in config  # file: pages need relative asset URLs
    assert 'outDir: "../field_tools/web"' in config
    assert f'target: "{BROWSER_TARGET}"' in config
    assert BROWSER_TARGET == "chrome108"
    assert "@vitejs/plugin-react" in config
    assert "@vitejs/plugin-react" not in content_of(
        plan_scaffold(options(web="vanilla")), "web/vite.config.ts"
    )


def test_the_page_loads_the_qt_channel_script_and_the_module_entry() -> None:
    for framework, entry in (("vanilla", "main.ts"), ("react", "main.tsx")):
        html = content_of(plan_scaffold(options(web=framework)), "web/index.html")
        assert 'src="qrc:///qtwebchannel/qwebchannel.js"' in html
        assert f'<script type="module" src="/src/{entry}"></script>' in html
        assert "<title>Field Tools</title>" in html


def test_the_checked_in_bindings_are_what_bridge_generate_renders(
    tmp_path: Path,
) -> None:
    """The generated client is source, owned by CI: --check must find no drift."""
    project = tmp_path / "field_tools"
    write_scaffold(options(web="vanilla"), project)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qgis_sdk_tools",
            "bridge",
            "generate",
            "--plugin",
            "field_tools.plugin:FieldToolsPlugin",
            "--out",
            "web/src/bridge.ts",
            "--check",
        ],
        cwd=project,
        env={**_clean_env(), "PYTHONPATH": layers.source_path()},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "up to date" in result.stdout


def test_the_transport_speaks_qwebchannel_and_knows_when_it_is_not_inside_qgis() -> (
    None
):
    transport = content_of(
        plan_scaffold(options(web="vanilla")), "web/src/transport.ts"
    )

    assert 'from "@archont561/qgis-sdk/bridge"' in transport
    assert "window.qt" in transport and "QWebChannel" in transport
    assert "export function insideQgis" in transport
    assert "export function connectWebChannel" in transport


def test_the_react_page_uses_the_sdk_bindings_over_the_generated_operations() -> None:
    plan = plan_scaffold(options(web="react"))
    app = content_of(plan, "web/src/App.tsx")
    test = content_of(plan, "web/src/App.test.tsx")

    assert 'from "@archont561/qgis-sdk/react"' in app
    assert "useOperations(createOperations)" in app
    assert 'from "@archont561/qgis-sdk/testing"' in test
    assert "createBridgeHarness" in test


def test_the_vanilla_page_tests_against_the_scripted_host() -> None:
    plan = plan_scaffold(options(web="vanilla"))

    assert "createBridgeHarness" in content_of(plan, "web/src/app.test.ts")
    assert "connectWebChannel" in content_of(plan, "web/src/main.ts")


# -- the Python half -----------------------------------------------------------


@pytest.mark.parametrize("placement", ["dialog", "dock"])
def test_the_plugin_opens_the_view_from_a_toolbar_action(placement: str) -> None:
    plan = plan_scaffold(options(web="vanilla", placement=placement))
    plugin = content_of(plan, "field_tools/plugin.py")
    view = content_of(plan, "field_tools/webview.py")

    assert f'placement="{placement}"' in plugin
    assert "def classFactory(iface" in plugin
    assert "from . import webview" in plugin
    assert "create_restricted_page" in view and "create_channel_object" in view
    assert "Dispatcher.from_runtime" in view
    assert "asset_roots=(ASSETS,)" in view
    assert "QDockWidget" in view and "QDialog" in view


@pytest.mark.parametrize("framework", ["vanilla", "react"])
def test_a_web_project_passes_check_without_native_exemptions(
    tmp_path: Path, framework: str
) -> None:
    project = tmp_path / "field_tools"
    write_scaffold(options(web=framework), project)

    report = check_project(project)

    assert report.diagnostics == (), [d.render() for d in report.diagnostics]


def test_the_web_projects_starter_tests_pass_without_qgis(tmp_path: Path) -> None:
    project = tmp_path / "field_tools"
    write_scaffold(options(web="react", placement="dock"), project)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project,
        env={
            **_clean_env(),
            "PYTHONPATH": layers.source_path(project),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout


def test_the_readme_tells_the_chosen_manager_how_to_build_the_page() -> None:
    readme = content_of(
        plan_scaffold(options(web="react", package_manager="pnpm")), "README.md"
    )

    assert "## Web UI" in readme
    assert "pnpm install" in readme
    assert "pnpm build" in readme
    assert "npm run" not in readme
    assert "field_tools/web/index.html" in readme


def test_the_project_declares_no_native_module_because_it_needs_none() -> None:
    pyproject = content_of(plan_scaffold(options(web="react")), "pyproject.toml")

    assert "native-modules" not in pyproject


# -- the commands the manager needs ----------------------------------------------


def test_install_and_script_commands_per_manager() -> None:
    assert install_command("npm") == ("npm", "install")
    assert install_command("pnpm") == ("pnpm", "install")
    assert install_command("bun") == ("bun", "install")
    assert script_command("npm", "build") == ("npm", "run", "build")
    assert script_command("pnpm", "build") == ("pnpm", "build")
    assert script_command("bun", "test") == ("bun", "run", "test")


def test_every_generated_web_file_ends_with_exactly_one_newline() -> None:
    for framework in ("vanilla", "react"):
        for file in plan_scaffold(options(web=framework)):
            assert file.content.endswith("\n"), file.path
            assert not file.content.endswith("\n\n"), file.path


def _clean_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTEST_", "QGIS", "PYTHONPATH"))
    }
