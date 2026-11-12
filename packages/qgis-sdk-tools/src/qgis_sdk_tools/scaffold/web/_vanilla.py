from __future__ import annotations

VANILLA_APP = """import { formStore, layersQuery, type QgisSdk } from "@archont561/qgis-sdk";
import type { VectorLayerInfo } from "@archont561/qgis-sdk/host";
import type { Operations, Streams } from "./bridge.schema";

/** The SDK this page is written against: the plugin's declared operations. */
export type PluginSdk = QgisSdk<Operations, Streams>;

const PAGE = `
	<h1>{title}</h1>
	<form id="ping-form">
		<fieldset id="ping-fields"></fieldset>
		<button id="ping" type="button">Ping</button>
		<output id="ping-result" for="ping"></output>
	</form>
	<p>
		<label>Layer <select id="layer"></select></label>
		<button id="layers" type="button">Refresh layers</button>
		<output id="layer-info" for="layer"></output>
	</p>
	<p id="error" role="alert"></p>
`;

/**
 * Render the page into `root`. Two stores from the SDK drive it: a form over
 * the declared `ping` action, whose fields come from the schema, and a layer
 * picker over the host's layer list, which says so when the page was not
 * granted it. No framework: the stores are subscribed to directly.
 */
export function createApp(root: HTMLElement, qgis: PluginSdk): void {
	root.innerHTML = PAGE;
	const error = element(root, "error");

	// One input per declared field of `ping`; the store validates and coerces.
	const ping = formStore(qgis, "ping", { initial: { value: 1 } });
	const fields = element(root, "ping-fields");
	for (const field of ping.fields) {
		const input = document.createElement("input");
		input.id = `ping-${field.name}`;
		input.name = field.name;
		input.type = NUMERIC.has(field.kind) ? "number" : "text";
		input.required = field.required;
		input.value = String(ping.getSnapshot().values[field.name] ?? "");
		input.addEventListener("input", () => ping.set(field.name, input.value));
		const label = document.createElement("label");
		label.append(`${field.label} `, input);
		fields.append(label);
	}
	element(root, "ping").addEventListener("click", () => void ping.submit());
	element(root, "ping-form").addEventListener("submit", (event) => {
		event.preventDefault();
		void ping.submit();
	});
	const pingResult = element(root, "ping-result");
	ping.subscribe((state) => {
		const { submission } = state;
		pingResult.textContent =
			submission.status === "ok"
				? String(submission.value)
				: submission.status === "pending"
					? "..."
					: "";
		error.textContent =
			submission.status === "error"
				? submission.error.message
				: state.submitted && !state.valid
					? Object.entries(state.errors)
							.map(([name, code]) => `${name}: ${code}`)
							.join(", ")
					: "";
	});

	// The picker reads the host, grant first: without `layers.read` in
	// `[tool.qgis-sdk.web] grants` the store is `refused` and no call is made.
	const layers = layersQuery(qgis);
	const select = element(root, "layer") as HTMLSelectElement;
	const info = element(root, "layer-info");
	let known: readonly VectorLayerInfo[] = [];
	layers.subscribe((state) => {
		switch (state.status) {
			case "ok":
				known = state.value;
				select.replaceChildren();
				for (const layer of known) {
					const option = document.createElement("option");
					option.value = layer.id;
					option.textContent = layer.name;
					select.append(option);
				}
				info.textContent = `${known.length} layer(s)`;
				break;
			case "refused":
				info.textContent = `${state.message}; add "layers.read" to the page's grants`;
				break;
			case "error":
				error.textContent = state.error.message;
				break;
			default:
				break;
		}
	});
	select.addEventListener("change", () => {
		const layer = known.find((candidate) => candidate.id === select.value);
		if (layer !== undefined) {
			info.textContent = `${layer.name} (${layer.geometry_type}, ${layer.crs ?? "no CRS"}, ${layer.field_names.length} field(s))`;
		}
	});
	element(root, "layers").addEventListener(
		"click",
		() => void layers.refresh(),
	);
	void layers.refresh();
}

const NUMERIC = new Set(["integer", "number", "metres", "range"]);

function element(root: HTMLElement, id: string): HTMLElement {
	const found = root.querySelector<HTMLElement>(`#${id}`);
	if (found === null) {
		throw new Error(`the page has no #${id} element`);
	}
	return found;
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
function operations(harness: {
	readonly calls: readonly { kind: string; operation: string }[];
}) {
	return harness.calls
		.filter((call) => call.kind !== "handshake")
		.map((call) => call.operation);
}

const LAYER = {
	id: "roads-1",
	name: "roads",
	geometry_type: "line" as const,
	crs: "EPSG:3857",
	field_names: ["id", "name"],
};

test("the ping form is built from the declaration and shows what the host answered", async () => {
	const harness = createBridgeHarness(schema);
	harness.expectInvoke("layers.list", () => ({
		items: [LAYER],
		truncated: false,
	}));
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	createApp(root, qgis);
	harness.expectInvoke("ping", (payload) => payload.value * 10);

	const value = root.querySelector<HTMLInputElement>("#ping-value");
	expect(value?.value).toBe("1");
	root.querySelector<HTMLButtonElement>("#ping")?.click();
	await harness.settled();
	const result = root.querySelector("#ping-result");
	await until(() => result?.textContent === "10");

	expect(result?.textContent).toBe("10");
	expect(operations(harness).sort()).toEqual(["layers.list", "ping"]);
	const info = root.querySelector("#layer-info");
	await until(() => info?.textContent === "1 layer(s)");
	expect(
		[...root.querySelectorAll("#layer option")].map(
			(option) => option.textContent,
		),
	).toEqual(["roads"]);
	harness.assertSatisfied();
	qgis.close();
});

test("an invalid value is refused on the page and never sent", async () => {
	const harness = createBridgeHarness(schema, { granted: [] });
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	createApp(root, qgis);

	const value = root.querySelector<HTMLInputElement>("#ping-value");
	if (value === null) {
		throw new Error("the form has no value input");
	}
	value.value = "";
	value.dispatchEvent(new Event("input"));
	root.querySelector<HTMLButtonElement>("#ping")?.click();
	await harness.settled();

	expect(root.querySelector("#error")?.textContent).toBe("value: required");
	expect(operations(harness)).toEqual([]);
	harness.assertSatisfied();
	qgis.close();
});

test("a page without the layers grant says so instead of calling the host", async () => {
	const harness = createBridgeHarness(schema, { granted: [] });
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	createApp(root, qgis);
	await harness.settled();
	const info = root.querySelector("#layer-info");
	await until(() => (info?.textContent ?? "") !== "");

	expect(info?.textContent).toContain("not granted layers.list");
	expect(operations(harness)).toEqual([]);
	harness.assertSatisfied();
	qgis.close();
});

test("a refusal from the host lands in the error line instead of a rejected promise", async () => {
	const harness = createBridgeHarness(schema);
	harness.expectInvoke("layers.list", () => fault("forbidden", "not yours"));
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	createApp(root, qgis);
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
// The SDK's web components: this import registers every <qgis-*> element
// (the typed React components are in "@archont561/qgis-sdk-ui/react"), the
// stylesheet styles them from the --qgis-sdk-* tokens applyHostTheme fills
// with the QGIS palette. Drop the three to go without.
import { applyHostTheme } from "@archont561/qgis-sdk-ui";
import "@archont561/qgis-sdk-ui/define";
import "@archont561/qgis-sdk-ui/style.css";
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
	void applyHostTheme(qgis);
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
