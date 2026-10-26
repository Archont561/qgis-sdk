/**
 * Mock evidence: the page drives the workflow in order and shows what the host
 * answered. Nothing here touches a QWebEngineView; that proof lives in the
 * plugin's Python tests and the workspace harness.
 */

import { QgisSdk } from "@archont561/qgis-sdk";
import { createBridgeHarness, fault } from "@archont561/qgis-sdk/testing";
import { expect, test } from "vitest";
import { createApp } from "./app";
import schema, {
	type BufferResult,
	type Open_fixtureResult,
} from "./bridge.schema";

const SOURCE: Open_fixtureResult = {
	id: "points-1",
	name: "points",
	geometry_type: "point",
	field_names: ["id", "value"],
	crs: "EPSG:4326",
};
const OUTPUT: BufferResult = {
	id: "buffer-1",
	name: "buffer",
	geometry_type: "polygon",
	field_names: ["id", "value"],
	crs: "EPSG:3857",
};

async function until(check: () => boolean): Promise<void> {
	for (let attempt = 0; attempt < 100 && !check(); attempt += 1) {
		await new Promise((resolve) => setTimeout(resolve, 1));
	}
}

function page() {
	// The harness is typed by the schema: an expectation names a declared
	// operation, sees its request and must answer with its result.
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const root = document.createElement("div");
	const state = createApp(root, qgis);
	const click = (id: string) =>
		root.querySelector<HTMLButtonElement>(`#${id}`)?.click();
	const text = (id: string) => root.querySelector(`#${id}`)?.textContent ?? "";
	return { harness, client: qgis, root, state, click, text };
}

/** The calls the page made, handshake aside. */
function operations(harness: {
	readonly calls: readonly { kind: string; operation: string }[];
}) {
	return harness.calls
		.filter((call) => call.kind !== "handshake")
		.map((call) => call.operation);
}

test("open, select, buffer and export go through the declared actions in order", async () => {
	const { harness, client, root, state, click, text } = page();
	harness.expectInvoke("open_fixture", () => SOURCE);
	harness.expectInvoke("selected_features", (payload) => {
		expect(payload.layer_id).toBe("points-1");
		return [1, 3];
	});
	harness.expectInvoke("buffer", (payload) => {
		expect(payload).toEqual({
			layer_id: "points-1",
			distance_metres: 500,
			working_crs: "EPSG:3857",
		});
		return OUTPUT;
	});
	harness.expectInvoke("export_layer", (payload) => {
		expect(payload).toEqual({
			layer_id: "buffer-1",
			file_name: "buffer.gpkg",
			overwrite: false,
		});
		return { path: "/exports/buffer.gpkg", driver: "GPKG" };
	});

	click("open");
	await until(() => text("source") !== "");
	click("selection");
	await until(() => text("selection-result") !== "");
	click("buffer");
	await until(() => text("buffer-result") !== "");
	click("export");
	await until(() => text("export-result") !== "");

	expect(text("source")).toBe("points (point, EPSG:4326)");
	expect(text("selection-result")).toBe("1, 3");
	expect(text("buffer-result")).toBe("buffer (polygon, EPSG:3857)");
	expect(text("export-result")).toBe("GPKG: /exports/buffer.gpkg");
	expect(state).toEqual({ sourceId: "points-1", outputId: "buffer-1" });
	expect(operations(harness)).toEqual([
		"open_fixture",
		"selected_features",
		"buffer",
		"export_layer",
	]);
	expect(root.querySelector("#error")?.textContent).toBe("");
	harness.assertSatisfied();
	client.close();
});

test("a buffer before the dataset is opened never reaches the host", async () => {
	const { harness, client, click, text } = page();

	click("buffer");
	await until(() => text("error") !== "");

	expect(text("error")).toBe("open the dataset first");
	expect(operations(harness)).toEqual([]);
	client.close();
});

test("a refusal from the host lands in the error line", async () => {
	const { harness, client, click, text } = page();
	harness.expectInvoke("open_fixture", () => SOURCE);
	harness.expectInvoke("buffer", () =>
		fault("algorithm_rejected", "working_crs is required"),
	);

	click("open");
	await until(() => text("source") !== "");
	click("buffer");
	await until(() => text("error") !== "");

	expect(text("error")).toContain("working_crs is required");
	expect(text("buffer-result")).toBe("");
	harness.assertSatisfied();
	client.close();
});

test("the export sends the overwrite choice and a bare file name only", async () => {
	const { harness, client, root, click, text } = page();
	harness.expectInvoke("open_fixture", () => SOURCE);
	harness.expectInvoke("buffer", () => OUTPUT);
	harness.expectInvoke("export_layer", (payload) => {
		expect(payload.overwrite).toBe(true);
		expect(payload.file_name).toBe("again.geojson");
		return { path: "/exports/again.geojson", driver: "GeoJSON" };
	});

	click("open");
	await until(() => text("source") !== "");
	click("buffer");
	await until(() => text("buffer-result") !== "");
	(root.querySelector("#file-name") as HTMLInputElement).value =
		"again.geojson";
	(root.querySelector("#overwrite") as HTMLInputElement).checked = true;
	click("export");
	await until(() => text("export-result") !== "");

	expect(text("export-result")).toBe("GeoJSON: /exports/again.geojson");
	harness.assertSatisfied();
	client.close();
});

test("a reply outside the declared result is refused by the SDK, not shown", async () => {
	const { harness, client, click, text } = page();
	harness.expectInvoke("open_fixture", () => ({ id: 1 }) as never);

	click("open");
	await until(() => text("error") !== "");

	expect(text("error")).toContain("open_fixture: the result");
	expect(text("source")).toBe("");
	harness.assertSatisfied();
	client.close();
});
