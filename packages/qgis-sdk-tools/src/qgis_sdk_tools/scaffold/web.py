"""The web half of a generated project: a Vite app and the view that shows it.

Everything here is text with a few validated values in it. The templates are
controlled (decision-18): every npm dependency is pinned to the exact version
this SDK release was qualified with, the Chromium target is the one the
oldest supported QGIS ships, and the page's schema module is rendered from
the plugin's own declarations so the checked-in bindings cannot drift from
them; the page builds its `QgisSdk` on that module (decision-44).
Bunup is the workspace's library tooling and never an application's: a Bun
project gets Vite and Vitest like the others.
"""

from __future__ import annotations

import json
from typing import Final

from qgis_sdk.declarations import action, describe_plugin, plugin

from qgis_sdk_tools.generate import generate_schema_typescript

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
"""The published bridge this scaffold is written against, pinned exactly.

``scripts/release.py stamp --scope typescript`` moves it with every bridge
release, so a tools release offers the newest bridge it was qualified with;
``WebOptions.sdk_dependency`` replaces it for a page inside this repository
(decision-41).
"""

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
    """Every file under ``web/`` for ``options.web``; the page view is the runtime's."""
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
            "web/src/bridge.schema.ts",
            generate_schema_typescript(describe_plugin(template_plugin_class(options))),
        ),
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


def bindings_command() -> str:
    """The drift check the project's CI runs, from the project root.

    The plugin class comes from ``[tool.qgis-sdk] plugin`` in the project's
    ``pyproject.toml`` (decision-43), so the command names only the output.
    """
    return "qgis-sdk bridge generate --out web/src/bridge.schema.ts --check"


def _package_json(options: ScaffoldOptions, web: WebOptions) -> str:
    react = web.framework == "react"
    dependencies: dict[str, str] = {
        SDK_NPM_PACKAGE: web.sdk_dependency or SDK_NPM_VERSION
    }
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
            "bindings": f"cd .. && {bindings_command()}",
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


VANILLA_MAIN = """import { QgisSdk } from "@archont561/qgis-sdk";
import { createApp } from "./app";
import schema from "./bridge.schema";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

// Three statements connect the page: the generated schema, the SDK built on
// it, the app. Outside a QGIS web view the SDK refuses at once, with the
// reason, instead of waiting for a channel that never comes.
try {
	createApp(root, QgisSdk.fromBridgeSchema(schema));
} catch (failure: unknown) {
	root.textContent =
		failure instanceof Error
			? `${failure.message}. Open this page from QGIS: outside a QGIS web view there is no host to talk to.`
			: String(failure);
}
"""

VANILLA_APP = """import type { QgisSdk } from "@archont561/qgis-sdk";
import type { Operations, Streams } from "./bridge.schema";

/** The SDK this page is written against: the plugin's declared operations. */
export type PluginSdk = QgisSdk<Operations, Streams>;

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

/** Render the page into `root`; every button goes through the SDK. */
export function createApp(root: HTMLElement, qgis: PluginSdk): void {
	root.innerHTML = PAGE;
	const pingResult = element(root, "ping-result");
	const layerList = element(root, "layer-list");
	const error = element(root, "error");
	let pings = 0;

	element(root, "ping").addEventListener("click", async () => {
		pings += 1;
		try {
			pingResult.textContent = String(await qgis.ping({ value: pings }));
		} catch (failure: unknown) {
			error.textContent = describe(failure);
		}
	});

	element(root, "layers").addEventListener("click", async () => {
		try {
			const ids = await qgis.project_layers();
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

import { QgisSdk } from "@archont561/qgis-sdk";
import { createBridgeHarness, fault } from "@archont561/qgis-sdk/testing";
import { expect, test } from "vitest";
import { createApp } from "./app";
import schema from "./bridge.schema";

async function until(check: () => boolean): Promise<void> {
	for (let attempt = 0; attempt < 100 && !check(); attempt += 1) {
		await new Promise((resolve) => setTimeout(resolve, 1));
	}
}

/** The operations the page called, handshake aside. */
function operations(harness: { readonly calls: readonly { kind: string; operation: string }[] }) {
	return harness.calls.filter((call) => call.kind !== "handshake").map((call) => call.operation);
}

test("the ping button shows what the host answered", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	createApp(root, qgis);
	harness.expectInvoke("ping", (payload) => payload.value * 10);

	root.querySelector<HTMLButtonElement>("#ping")?.click();
	await harness.settled();
	const result = root.querySelector("#ping-result");
	await until(() => result?.textContent === "10");

	expect(result?.textContent).toBe("10");
	expect(operations(harness)).toEqual(["ping"]);
	harness.assertSatisfied();
	qgis.close();
});

test("a refusal lands in the error line instead of a rejected promise", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	createApp(root, qgis);
	harness.expectInvoke("project_layers", () => fault("forbidden", "not yours"));

	root.querySelector<HTMLButtonElement>("#layers")?.click();
	await harness.settled();
	const error = root.querySelector("#error");
	await until(() => (error?.textContent ?? "") !== "");

	expect(error?.textContent).toContain("not yours");
	harness.assertSatisfied();
	qgis.close();
});
"""

REACT_MAIN = """import { QgisSdk } from "@archont561/qgis-sdk";
import { BridgeProvider } from "@archont561/qgis-sdk/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import schema from "./bridge.schema";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

// Three statements connect the page: the generated schema, the SDK built on
// it, the app under a provider that shares it. Outside a QGIS web view the
// SDK refuses at once, with the reason.
try {
	const qgis = QgisSdk.fromBridgeSchema(schema);
	createRoot(root).render(
		<StrictMode>
			<BridgeProvider qgis={qgis}>
				<App />
			</BridgeProvider>
		</StrictMode>,
	);
} catch (failure: unknown) {
	root.textContent =
		failure instanceof Error
			? `${failure.message}. Open this page from QGIS: outside a QGIS web view there is no host to talk to.`
			: String(failure);
}
"""

REACT_APP = """import { useOperation, useQgisSdk } from "@archont561/qgis-sdk/react";
import { useState } from "react";
import type { Operations, Streams } from "./bridge.schema";

/** The page: two declared operations, driven through the SDK's hooks. */
export function App() {
	const qgis = useQgisSdk<Operations, Streams>();
	const [ping, runPing] = useOperation(qgis.ping);
	const [layers, loadLayers] = useOperation(qgis.project_layers);
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

import { QgisSdk } from "@archont561/qgis-sdk";
import { BridgeProvider } from "@archont561/qgis-sdk/react";
import { createBridgeHarness } from "@archont561/qgis-sdk/testing";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, test } from "vitest";
import { App } from "./App";
import schema from "./bridge.schema";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

test("the ping button shows what the host answered", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	harness.expectInvoke("ping", (payload) => payload.value * 10);
	const container = document.createElement("div");
	const root = createRoot(container);
	await act(async () => {
		root.render(
			<BridgeProvider qgis={qgis}>
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
	const operations = harness.calls.filter((call) => call.kind !== "handshake");
	expect(operations.map((call) => call.operation)).toEqual(["ping"]);
	harness.assertSatisfied();
	await act(async () => {
		root.unmount();
	});
	qgis.close();
});
"""
