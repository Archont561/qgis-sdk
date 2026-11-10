/**
 * The command transcripts the guides replay, taken from real runs of the
 * scaffold rather than written by hand.
 *
 * `scaffold` is what `qgis-sdk new my_tools --title "My Tools" --no-input`
 * wrote on 2026-11-10 (contents trimmed to the parts a reader acts on).
 * `check` is the output of the same project after a toolbar icon was named that
 * does not exist and an action with inputs was placed on a toolbar - the two
 * codes a first plugin actually meets.
 */

export interface WalkthroughFile {
	readonly path: string;
	readonly content: string;
}

export interface Walkthrough {
	/** The command a reader typed, shown as the transcript's prompt. */
	readonly command: string;
	/** The files the command wrote or that the output talks about. */
	readonly files: readonly WalkthroughFile[];
	/** The lines the command printed, if the point of the command is its output. */
	readonly terminal?: readonly string[];
	/** What the reader is looking at, printed under the widget. */
	readonly caption: string;
}

const PYPROJECT = `[project]
name = "my_tools"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["qgis-sdk-runtime>=0.11,<0.12"]

[dependency-groups]
dev = ["qgis-sdk-tools>=0.11,<0.12"]

[tool.qgis-sdk]
plugin = "my_tools.plugin:app"
hosts = ["desktop"]
qgis-minimum-version = "4.0"
experimental = true

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-p qgis_sdk_tools.pytest_plugin"`;

const PLUGIN = `"""My Tools: a minimal qgis-sdk plugin."""

from __future__ import annotations

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext


app = QgisSdkPlugin(id="my_tools", title="My Tools")


@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> int:
    """Return the value unchanged so a caller can prove the round trip."""
    return value


@app.action(id="project_layers", title="Project layers")
def project_layers(ctx: PluginContext) -> list[str]:
    """The same project service a web view reaches as \`\`host.project\`\`."""
    return list(ctx.project.layer_ids())`;

const TEST = `"""Smoke tests for My Tools. They need no QGIS install and no display."""

import pytest
from qgis_sdk import describe
from qgis_sdk.adapters.desktop import host

from my_tools.plugin import app

classFactory = host("my_tools.plugin:app")


def test_the_plugin_starts_and_unloads_without_a_host() -> None:
    plugin = classFactory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.state.value == "running"
        assert plugin.runtime.actions["ping"](7) == 7
    finally:
        plugin.unload()
    assert plugin.runtime.state.value == "stopped"


def test_declared_actions_are_the_plugins_public_surface() -> None:
    description = describe(app)

    assert [action.id for action in description.actions] == ["ping", "project_layers"]`;

const BROKEN_PLUGIN = `from qgis_sdk import QgisSdkPlugin, toolbar

app = QgisSdkPlugin(id="my_tools", title="My Tools")


@toolbar(icon="ping.svg", text="Ping")      # no my_tools/icons/ping.svg
@app.action(id="ping_many", title="Ping many")
def ping_many(ctx: PluginContext, value: int, times: int) -> list[int]:
    """Two inputs, and a toolbar button that cannot collect them."""
    return [value] * times`;

export const WALKTHROUGHS: Record<string, Walkthrough> = {
	scaffold: {
		command: 'qgis-sdk new my_tools --title "My Tools" --no-input',
		files: [
			{ path: "pyproject.toml", content: PYPROJECT },
			{ path: "my_tools/plugin.py", content: PLUGIN },
			{ path: "tests/test_plugin.py", content: TEST },
		],
		caption:
			"Three files carry the plugin. Everything else `qgis-sdk build` needs - metadata.txt, the QGIS entry point, the vendored runtime - is derived from them.",
	},
	check: {
		command: "qgis-sdk check",
		files: [{ path: "my_tools/plugin.py", content: BROKEN_PLUGIN }],
		terminal: [
			"my_tools/plugin.py:6:15: ICON001 @toolbar icon 'ping.svg' is not a file under my_tools/icons/",
			"    Add my_tools/icons/ping.svg to the package (a file name, not a path), or fix the name; QGIS loads it at initGui.",
			"my_tools/plugin.py:8:1: UI003 ping_many is bound to the Desktop (@toolbar) but takes inputs (value, times); nothing collects them",
			"    Move the binding to a Dialog/Dock surface that calls self.ctx.actions.ping_many(...), or drop the inputs; the host refuses a typed trigger by name and never generates a dialog.",
			"checked 3 files: 2 problems",
		],
		caption:
			"A code, a line, and the fix. `qgis-sdk check --json` prints the same findings for a tool; nothing about it needs QGIS.",
	},
};
