from __future__ import annotations

REACT_APP = """import { layersQuery } from "@archont561/qgis-sdk";
import type { VectorLayerInfo } from "@archont561/qgis-sdk/host";
import { useForm, useHostQuery, useQgisSdk } from "@archont561/qgis-sdk/react";
import { useMemo, useState } from "react";
import type { Operations, Streams } from "./bridge.schema";

const NUMERIC = new Set(["integer", "number", "metres", "range"]);

/**
 * The page: a form over the declared `ping` action, whose fields come from
 * the schema, and a layer picker over the host's layer list, which says so
 * when the page was not granted it. Both are stores from the SDK read
 * through the React hooks.
 */
export function App() {
	const qgis = useQgisSdk<Operations, Streams>();
	const [ping, form] = useForm(qgis, "ping", { initial: { value: 1 } });
	const [layers] = useHostQuery(useMemo(() => layersQuery(qgis), [qgis]));
	const [selected, setSelected] = useState<VectorLayerInfo | null>(null);

	return (
		<main>
			<h1>{title}</h1>
			<form
				onSubmit={(event) => {
					event.preventDefault();
					void form.submit();
				}}
			>
				{form.fields.map((field) => (
					<label key={field.name}>
						{field.label}{" "}
						<input
							name={field.name}
							type={NUMERIC.has(field.kind) ? "number" : "text"}
							required={field.required}
							value={String(ping.values[field.name] ?? "")}
							onChange={(event) => form.set(field.name, event.target.value)}
						/>
					</label>
				))}
				<button type="button" onClick={() => void form.submit()}>
					Ping
				</button>{" "}
				<output>{describe(ping.submission)}</output>
			</form>
			<p>
				<label>
					Layer{" "}
					<select
						onChange={(event) =>
							setSelected(
								layers.status === "ok"
									? (layers.value.find(
											(layer) => layer.id === event.target.value,
										) ?? null)
									: null,
							)
						}
					>
						{layers.status === "ok"
							? layers.value.map((layer) => (
									<option key={layer.id} value={layer.id}>
										{layer.name}
									</option>
								))
							: null}
					</select>
				</label>
				<output>
					{layers.status === "refused"
						? `${layers.message}; add "layers.read" to the page's grants`
						: selected === null
							? layers.status === "ok"
								? `${layers.value.length} layer(s)`
								: ""
							: `${selected.name} (${selected.geometry_type}, ${selected.crs ?? "no CRS"}, ${selected.field_names.length} field(s))`}
				</output>
			</p>
			<p role="alert">
				{ping.submission.status === "error"
					? ping.submission.error.message
					: ping.submitted && !ping.valid
						? Object.entries(ping.errors)
								.map(([name, code]) => `${name}: ${code}`)
								.join(", ")
						: layers.status === "error"
							? layers.error.message
							: ""}
			</p>
		</main>
	);
}

function describe(state: { status: string; value?: unknown }): string {
	switch (state.status) {
		case "ok":
			return String(state.value);
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
import schema, { type Operations, type Streams } from "./bridge.schema";

(
	globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const LAYER = {
	id: "roads-1",
	name: "roads",
	geometry_type: "line" as const,
	crs: "EPSG:3857",
	field_names: ["id", "name"],
};

/** The operations the page called, handshake aside. */
function operations(harness: {
	readonly calls: readonly { kind: string; operation: string }[];
}) {
	return harness.calls
		.filter((call) => call.kind !== "handshake")
		.map((call) => call.operation);
}

async function mount(qgis: QgisSdk<Operations, Streams>) {
	const container = document.createElement("div");
	const root = createRoot(container);
	await act(async () => {
		root.render(
			<BridgeProvider qgis={qgis}>
				<App />
			</BridgeProvider>,
		);
	});
	return {
		container,
		unmount: () =>
			act(async () => {
				root.unmount();
			}),
	};
}

test("the ping form is built from the declaration and shows what the host answered", async () => {
	const harness = createBridgeHarness(schema);
	harness.expectInvoke("layers.list", () => ({
		items: [LAYER],
		truncated: false,
	}));
	harness.expectInvoke("ping", (payload) => payload.value * 10);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const { container, unmount } = await mount(qgis);
	await act(async () => {
		await harness.settled();
	});

	expect(
		container.querySelector<HTMLInputElement>("input[name=value]")?.value,
	).toBe("1");
	expect(
		[...container.querySelectorAll("option")].map(
			(option) => option.textContent,
		),
	).toEqual(["roads"]);
	await act(async () => {
		container.querySelector<HTMLButtonElement>("button")?.click();
	});
	await act(async () => {
		await harness.settled();
	});

	expect(container.querySelector("output")?.textContent).toBe("10");
	expect(operations(harness).sort()).toEqual(["layers.list", "ping"]);
	harness.assertSatisfied();
	await unmount();
	qgis.close();
});

test("a page without the layers grant says so instead of calling the host", async () => {
	const harness = createBridgeHarness(schema, { granted: [] });
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const { container, unmount } = await mount(qgis);
	await act(async () => {
		await harness.settled();
	});

	expect(container.querySelectorAll("output")[1]?.textContent).toContain(
		"not granted layers.list",
	);
	expect(operations(harness)).toEqual([]);
	harness.assertSatisfied();
	await unmount();
	qgis.close();
});
"""
