"""The web half of a generated project: a Vite app and the view that shows it.

Everything here is text with a few validated values in it. The templates are
controlled (decision-18): every npm dependency is pinned to the exact version
this SDK release was qualified with, the Chromium target is the one the
oldest supported QGIS ships, and the page's typed client is rendered from the
plugin's own declarations so the checked-in bindings cannot drift from them.
Bunup is the workspace's library tooling and never an application's: a Bun
project gets Vite and Vitest like the others.
"""

from __future__ import annotations

import json
from typing import Final

from qgis_sdk.bridge.generate import generate_typescript
from qgis_sdk.declarations import action, describe_plugin, plugin

from .options import PackageManager, ScaffoldOptions, WebOptions

__all__ = [
    "BROWSER_TARGET",
    "SDK_NPM_PACKAGE",
    "SDK_NPM_VERSION",
    "WEB_TEMPLATE_VERSIONS",
    "WebFile",
    "install_command",
    "plan_web",
    "script_command",
    "template_plugin_class",
]

LF: Final = "\n"

SDK_NPM_PACKAGE: Final = "@archont561/qgis-sdk"
SDK_NPM_VERSION: Final = "0.3.0"
"""The published bridge this scaffold is written against, pinned exactly."""

# Qt WebEngine is Chromium: Qt 6.5 (the oldest Qt 6 LTS a QGIS 4 may ship)
# carries Chromium 108. Raise this with qgisMinimumVersion, never above it.
BROWSER_TARGET: Final = "chrome108"

WEB_TEMPLATE_VERSIONS: Final[dict[str, str]] = {
    "typescript": "7.0.2",
    "vite": "8.3.5",
    "vitest": "5.0.5",
    "happy-dom": "21.0.4",
    "react": "19.3.1",
    "react-dom": "19.3.1",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.2",
}
"""Exact versions the generated ``package.json`` pins (controlled templates)."""

WebFile = tuple[str, str]
"""A project-relative path and its content; ``generate`` wraps it."""


def install_command(package_manager: PackageManager) -> tuple[str, ...]:
    """The install step for one manager, run inside ``web/``."""
    return (package_manager, "install")


def script_command(package_manager: PackageManager, script: str) -> tuple[str, ...]:
    """How one manager runs a ``package.json`` script."""
    if package_manager == "pnpm":
        return ("pnpm", script)
    return (package_manager, "run", script)


def template_plugin_class(options: ScaffoldOptions) -> type:
    """The declarations ``plugin.py`` carries, as a class the generator can read.

    This mirrors ``PLUGIN_MODULE`` in :mod:`.generate` action for action; the
    scaffold test that runs ``bridge generate --check`` against a written
    project is what keeps the two in step.
    """

    @plugin(id=options.plugin, title=options.title)
    class Template:
        @action(id="ping", title="Ping")
        def ping(self, value: int) -> int:
            return value

        @action(id="project_layers", title="Project layers")
        def project_layers(self) -> list[str]:
            return []

    return Template


def plan_web(options: ScaffoldOptions) -> tuple[WebFile, ...]:
    """Every file under ``web/`` plus the Python view module, for ``options.web``."""
    web = options.web
    if web is None:
        return ()
    files: list[WebFile] = [
        ("web/package.json", _package_json(options, web)),
        ("web/vite.config.ts", _vite_config(options, web)),
        ("web/tsconfig.json", _tsconfig(web)),
        ("web/index.html", _index_html(options, web)),
        ("web/.gitignore", "node_modules/\n"),
        (
            "web/src/bridge.ts",
            generate_typescript(describe_plugin(template_plugin_class(options))),
        ),
        ("web/src/transport.ts", TRANSPORT),
        (f"{options.plugin}/webview.py", _webview(options)),
    ]
    if web.framework == "react":
        files += [
            ("web/src/main.tsx", REACT_MAIN),
            ("web/src/App.tsx", REACT_APP.replace("{title}", options.title)),
            ("web/src/App.test.tsx", REACT_TEST),
        ]
    else:
        files += [
            ("web/src/main.ts", VANILLA_MAIN),
            ("web/src/app.ts", VANILLA_APP.replace("{title}", options.title)),
            ("web/src/app.test.ts", VANILLA_TEST),
        ]
    return tuple(files)


def bindings_command(options: ScaffoldOptions) -> str:
    """The drift check the project's CI runs, from the project root."""
    class_name = "".join(word.capitalize() for word in options.plugin.split("_"))
    return (
        "qgis-sdk bridge generate "
        f"--plugin {options.plugin}.plugin:{class_name}Plugin "
        "--out web/src/bridge.ts --check"
    )


def _package_json(options: ScaffoldOptions, web: WebOptions) -> str:
    react = web.framework == "react"
    dependencies: dict[str, str] = {SDK_NPM_PACKAGE: SDK_NPM_VERSION}
    dev_dependencies = {
        name: WEB_TEMPLATE_VERSIONS[name]
        for name in ("happy-dom", "typescript", "vite", "vitest")
    }
    if react:
        dependencies.update(
            react=WEB_TEMPLATE_VERSIONS["react"],
            **{"react-dom": WEB_TEMPLATE_VERSIONS["react-dom"]},
        )
        dev_dependencies.update(
            {
                name: WEB_TEMPLATE_VERSIONS[name]
                for name in ("@types/react", "@types/react-dom", "@vitejs/plugin-react")
            }
        )
    package = {
        "name": f"{options.plugin}-web",
        "private": True,
        "version": options.version,
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "test": "vitest run",
            "typecheck": "tsc --noEmit",
            "bindings": f"cd .. && {bindings_command(options)}",
        },
        "dependencies": dict(sorted(dependencies.items())),
        "devDependencies": dict(sorted(dev_dependencies.items())),
    }
    return json.dumps(package, indent="\t") + LF


def _vite_config(options: ScaffoldOptions, web: WebOptions) -> str:
    react = web.framework == "react"
    imports = 'import { defineConfig } from "vitest/config";\n'
    plugins = ""
    if react:
        imports = 'import react from "@vitejs/plugin-react";\n' + imports
        plugins = "\tplugins: [react()],\n"
    return (
        f"{imports}\n"
        "// QGIS shows the page in Qt WebEngine, which is Chromium: Qt 6.5's is\n"
        "// Chromium 108. Raise the target together with qgisMinimumVersion, never\n"
        "// above what the oldest QGIS you support ships.\n"
        "export default defineConfig({\n"
        f"{plugins}"
        '\tbase: "./",\n'
        "\tbuild: {\n"
        f'\t\toutDir: "../{options.plugin}/web",\n'
        "\t\temptyOutDir: true,\n"
        f'\t\ttarget: "{BROWSER_TARGET}",\n'
        "\t},\n"
        "\ttest: {\n"
        '\t\tenvironment: "happy-dom",\n'
        "\t},\n"
        "});\n"
    )


def _tsconfig(web: WebOptions) -> str:
    compiler: dict[str, object] = {
        "target": "ES2022",
        "lib": ["ES2022", "DOM", "DOM.Iterable"],
        "module": "ESNext",
        "moduleResolution": "bundler",
        "types": ["vite/client"],
        "strict": True,
        "noEmit": True,
        "isolatedModules": True,
        "skipLibCheck": True,
    }
    if web.framework == "react":
        compiler["jsx"] = "react-jsx"
    return (
        json.dumps({"compilerOptions": compiler, "include": ["src"]}, indent="\t") + LF
    )


def _index_html(options: ScaffoldOptions, web: WebOptions) -> str:
    entry = "main.tsx" if web.framework == "react" else "main.ts"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "\t<head>\n"
        '\t\t<meta charset="utf-8" />\n'
        f"\t\t<title>{options.title}</title>\n"
        "\t\t<!-- Qt serves this inside QGIS; outside, the page notices it is missing. -->\n"
        '\t\t<script src="qrc:///qtwebchannel/qwebchannel.js"></script>\n'
        "\t</head>\n"
        "\t<body>\n"
        '\t\t<div id="app"></div>\n'
        f'\t\t<script type="module" src="/src/{entry}"></script>\n'
        "\t</body>\n"
        "</html>\n"
    )


TRANSPORT = """/**
 * The wire between this page and the plugin: Qt's WebChannel, nothing else.
 *
 * QGIS registers one object named "bridge" on the channel (see webview.py). Its
 * `receive` slot takes a JSON envelope; its `message` signal carries every
 * reply and stream frame back. Vitest never sees this file: the tests hand the
 * same client a scripted host from `@archont561/qgis-sdk/testing` instead.
 */

import type { WireTransport } from "@archont561/qgis-sdk/bridge";

interface ChannelObject {
	receive(text: string): void;
	readonly message: {
		connect(listener: (text: string) => void): void;
		disconnect(listener: (text: string) => void): void;
	};
}

interface Channel {
	readonly objects: Readonly<Record<string, ChannelObject | undefined>>;
}

declare global {
	interface Window {
		qt?: { readonly webChannelTransport: unknown };
		QWebChannel?: new (transport: unknown, ready: (channel: Channel) => void) => unknown;
	}
}

/** True inside a QGIS web view, where Qt injected its transport and script. */
export function insideQgis(): boolean {
	return (
		typeof window !== "undefined" &&
		window.qt !== undefined &&
		typeof window.QWebChannel === "function"
	);
}

/** Resolve a transport once the channel is ready; reject outside QGIS. */
export function connectWebChannel(objectName = "bridge"): Promise<WireTransport> {
	return new Promise((resolve, reject) => {
		if (!insideQgis() || window.qt === undefined || window.QWebChannel === undefined) {
			reject(new Error("not inside a QGIS web view: window.qt is missing"));
			return;
		}
		new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
			const object = channel.objects[objectName];
			if (object === undefined) {
				reject(new Error(`the host registered no "${objectName}" channel object`));
				return;
			}
			resolve({
				send: (message) => object.receive(JSON.stringify(message)),
				subscribe: (listener) => {
					const forward = (text: string) => listener(JSON.parse(text));
					object.message.connect(forward);
					return () => object.message.disconnect(forward);
				},
			});
		});
	});
}
"""

VANILLA_MAIN = """import { BridgeClient } from "@archont561/qgis-sdk/bridge";
import { createApp } from "./app";
import { createOperations } from "./bridge";
import { connectWebChannel, insideQgis } from "./transport";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

if (insideQgis()) {
	connectWebChannel().then(
		(transport) => createApp(root, createOperations(new BridgeClient(transport))),
		(failure: unknown) => {
			root.textContent = failure instanceof Error ? failure.message : String(failure);
		},
	);
} else {
	root.textContent =
		"Open this page from QGIS: outside a QGIS web view there is no host to talk to.";
}
"""

VANILLA_APP = """import type { PluginOperations } from "./bridge";

const PAGE = `
	<h1>{title}</h1>
	<p>
		<button id="ping" type="button">Ping</button>
		<output id="ping-result" for="ping"></output>
	</p>
	<p><button id="layers" type="button">Project layers</button></p>
	<ul id="layer-list"></ul>
	<p id="error" role="alert"></p>
`;

/** Render the page into `root`; every button goes through the generated client. */
export function createApp(root: HTMLElement, operations: PluginOperations): void {
	root.innerHTML = PAGE;
	const pingResult = element(root, "ping-result");
	const layerList = element(root, "layer-list");
	const error = element(root, "error");
	let pings = 0;

	element(root, "ping").addEventListener("click", async () => {
		pings += 1;
		try {
			pingResult.textContent = String(await operations.ping({ value: pings }));
		} catch (failure: unknown) {
			error.textContent = describe(failure);
		}
	});

	element(root, "layers").addEventListener("click", async () => {
		try {
			const ids = await operations.project_layers();
			layerList.replaceChildren(
				...ids.map((id) => {
					const item = document.createElement("li");
					item.textContent = id;
					return item;
				}),
			);
		} catch (failure: unknown) {
			error.textContent = describe(failure);
		}
	});
}

function element(root: HTMLElement, id: string): HTMLElement {
	const found = root.querySelector<HTMLElement>(`#${id}`);
	if (found === null) {
		throw new Error(`the page has no #${id} element`);
	}
	return found;
}

function describe(failure: unknown): string {
	return failure instanceof Error ? failure.message : String(failure);
}
"""

VANILLA_TEST = """/**
 * Mock evidence: the page handles what a host could answer. Nothing here
 * touches a QWebEngineView; that proof lives in the plugin's Python tests.
 */

import { BridgeClient } from "@archont561/qgis-sdk/bridge";
import { createBridgeHarness, fault } from "@archont561/qgis-sdk/testing";
import { expect, test } from "vitest";
import { createApp } from "./app";
import { createOperations, type OperationId, type PingRequest } from "./bridge";

async function until(check: () => boolean): Promise<void> {
	for (let attempt = 0; attempt < 100 && !check(); attempt += 1) {
		await new Promise((resolve) => setTimeout(resolve, 1));
	}
}

test("the ping button shows what the host answered", async () => {
	const harness = createBridgeHarness<OperationId>();
	const client = new BridgeClient(harness);
	const root = document.createElement("div");
	createApp(root, createOperations(client));
	harness.expectInvoke<PingRequest, number>("ping", (payload) => payload.value * 10);

	root.querySelector<HTMLButtonElement>("#ping")?.click();
	await harness.settled();
	const result = root.querySelector("#ping-result");
	await until(() => result?.textContent === "10");

	expect(result?.textContent).toBe("10");
	expect(harness.calls.map((call) => call.operation)).toEqual(["ping"]);
	harness.assertSatisfied();
	client.close();
});

test("a refusal lands in the error line instead of a rejected promise", async () => {
	const harness = createBridgeHarness<OperationId>();
	const client = new BridgeClient(harness);
	const root = document.createElement("div");
	createApp(root, createOperations(client));
	harness.expectInvoke("project_layers", () => fault("forbidden", "not yours"));

	root.querySelector<HTMLButtonElement>("#layers")?.click();
	await harness.settled();
	const error = root.querySelector("#error");
	await until(() => (error?.textContent ?? "") !== "");

	expect(error?.textContent).toContain("not yours");
	harness.assertSatisfied();
	client.close();
});
"""

REACT_MAIN = """import { BridgeProvider } from "@archont561/qgis-sdk/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { connectWebChannel, insideQgis } from "./transport";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

if (insideQgis()) {
	connectWebChannel().then(
		(transport) => {
			createRoot(root).render(
				<StrictMode>
					<BridgeProvider transport={transport}>
						<App />
					</BridgeProvider>
				</StrictMode>,
			);
		},
		(failure: unknown) => {
			root.textContent = failure instanceof Error ? failure.message : String(failure);
		},
	);
} else {
	root.textContent =
		"Open this page from QGIS: outside a QGIS web view there is no host to talk to.";
}
"""

REACT_APP = """import { useOperation, useOperations } from "@archont561/qgis-sdk/react";
import { useState } from "react";
import { createOperations } from "./bridge";

/** The page: two declared operations, driven through the SDK's hooks. */
export function App() {
	const operations = useOperations(createOperations);
	const [ping, runPing] = useOperation(operations.ping);
	const [layers, loadLayers] = useOperation(operations.project_layers);
	const [count, setCount] = useState(0);

	return (
		<main>
			<h1>{title}</h1>
			<p>
				<button
					type="button"
					onClick={() => {
						const next = count + 1;
						setCount(next);
						void runPing({ value: next });
					}}
				>
					Ping
				</button>{" "}
				<output>{describe(ping)}</output>
			</p>
			<p>
				<button type="button" onClick={() => void loadLayers({})}>
					Project layers
				</button>
			</p>
			<ul>{layers.status === "ok" ? layers.value.map((id) => <li key={id}>{id}</li>) : null}</ul>
			<p role="alert">{layers.status === "error" ? layers.error.message : ""}</p>
		</main>
	);
}

function describe(state: { status: string; value?: unknown; error?: Error }): string {
	switch (state.status) {
		case "ok":
			return String(state.value);
		case "error":
			return state.error?.message ?? "failed";
		case "pending":
			return "...";
		default:
			return "";
	}
}
"""

REACT_TEST = """/**
 * Mock evidence: the page handles what a host could answer. Nothing here
 * touches a QWebEngineView; that proof lives in the plugin's Python tests.
 */

import { BridgeProvider } from "@archont561/qgis-sdk/react";
import { createBridgeHarness } from "@archont561/qgis-sdk/testing";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, test } from "vitest";
import { App } from "./App";
import type { OperationId, PingRequest } from "./bridge";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

test("the ping button shows what the host answered", async () => {
	const harness = createBridgeHarness<OperationId>();
	harness.expectInvoke<PingRequest, number>("ping", (payload) => payload.value * 10);
	const container = document.createElement("div");
	const root = createRoot(container);
	await act(async () => {
		root.render(
			<BridgeProvider transport={harness}>
				<App />
			</BridgeProvider>,
		);
	});

	await act(async () => {
		container.querySelector<HTMLButtonElement>("button")?.click();
	});
	await act(async () => {
		await harness.settled();
	});

	expect(container.querySelector("output")?.textContent).toBe("10");
	expect(harness.calls.map((call) => call.operation)).toEqual(["ping"]);
	harness.assertSatisfied();
	await act(async () => {
		root.unmount();
	});
});
"""

WEBVIEW = '''"""The web page: a restricted Qt WebEngine view over this plugin's own bridge.

Qt and the SDK's native adapters are imported inside the functions, so
`qgis-sdk check` and the starter tests import this package without QGIS;
QGIS calls the functions with its ``iface``. The page may load files from
``web/`` only and reach no remote origin until you grant one in
``BrowserPolicy``.

Under `qgis-sdk dev` the Vite dev server serves the page instead, with hot
module replacement: the command puts its origin in ``QGIS_SDK_DEV_SERVER``
for the QGIS process it starts, and only there. A built plugin never sees the
variable and never reaches a dev server.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qgis_sdk.bridge import Dispatcher

ASSETS = Path(__file__).resolve().parent / "web"  # `{build}` in web/ writes it
INDEX = ASSETS / "index.html"
VIEW_ID = "{plugin}.main"
CHANNEL_OBJECT = "bridge"  # the name web/src/transport.ts looks up
TITLE = "{title}"
DEV_SERVER_ENV = "QGIS_SDK_DEV_SERVER"


def dev_server() -> str | None:
    """The Vite origin `qgis-sdk dev` is serving the page from, if any."""
    return os.environ.get(DEV_SERVER_ENV) or None


def add_toolbar_action(
    iface: Any, title: str, on_trigger: Callable[[], None]
) -> Any | None:
    """Put one button on the QGIS toolbar; a host without ``iface`` gets none."""
    if iface is None:
        return None
    from qgis.PyQt.QtWidgets import QAction

    action = QAction(title, iface.mainWindow())
    action.triggered.connect(lambda _checked=False: on_trigger())
    iface.addToolBarIcon(action)
    return action


def remove_toolbar_action(iface: Any, action: Any | None) -> None:
    """Take the button down again on unload."""
    if iface is None or action is None:
        return
    iface.removeToolBarIcon(action)
    action.deleteLater()


def open_view(runtime: Any, iface: Any, *, placement: str) -> Any:
    """Build the page, its channel and the widget QGIS shows; return the widget.

    ``runtime`` is the SDK's ``PluginRuntime``: its description is the
    allowlist and its bound actions are the handlers, so the page can call
    exactly what ``plugin.py`` declares and nothing else.
    """
    from qgis.PyQt.QtCore import Qt, QUrl
    from qgis.PyQt.QtWebChannel import QWebChannel
    from qgis.PyQt.QtWidgets import QDialog, QDockWidget, QVBoxLayout
    from qgis_sdk.adapters.webchannel import create_channel_object
    from qgis_sdk.adapters.webengine import (
        BrowserPolicy,
        create_restricted_page,
        create_webengine_view,
    )

    served_from = dev_server()
    dispatcher = Dispatcher.from_runtime(
        runtime, authorize=lambda binding, operation: binding.view_id == VIEW_ID
    )
    binding = dispatcher.bind(
        view_id=VIEW_ID, origin=served_from or ASSETS.as_uri()
    )
    policy = BrowserPolicy(
        origins=() if served_from is None else (served_from,),
        asset_roots=(ASSETS,) if ASSETS.is_dir() else (),
    )
    view = create_webengine_view()
    page = create_restricted_page(policy, parent=view)
    channel = QWebChannel(page)
    channel.registerObject(
        CHANNEL_OBJECT, create_channel_object(dispatcher, binding, parent=page)
    )
    page.setWebChannel(channel)
    view.setPage(page)
    if served_from is not None:
        page.load(QUrl(served_from + "/"))
    elif INDEX.is_file():
        page.load(QUrl.fromLocalFile(str(INDEX)))
    else:
        page.setHtml(
            f"<p>No built page at <code>{INDEX}</code>. "
            "Run <code>{build}</code> in <code>web/</code> first.</p>"
        )

    parent = None if iface is None else iface.mainWindow()
    if placement == "dock":
        dock = QDockWidget(TITLE, parent)
        dock.setObjectName(VIEW_ID)
        dock.setWidget(view)
        if iface is not None:
            iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        return dock
    dialog = QDialog(parent)
    dialog.setWindowTitle(TITLE)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    dialog.resize(720, 540)
    return dialog


def close_view(widget: Any, iface: Any) -> None:
    """Close the page and release the widget, dock or dialog alike."""
    from qgis.PyQt.QtWidgets import QDockWidget

    if iface is not None and isinstance(widget, QDockWidget):
        iface.removeDockWidget(widget)
    widget.close()
    widget.deleteLater()
'''


def _webview(options: ScaffoldOptions) -> str:
    assert options.web is not None
    build = " ".join(script_command(options.web.package_manager, "build"))
    return (
        WEBVIEW.replace("{plugin}", options.plugin)
        .replace("{title}", options.title)
        .replace("{build}", build)
    )
