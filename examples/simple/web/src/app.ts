import type { QgisSdk } from "@archont561/qgis-sdk";
import type { Operations, Streams } from "./bridge.schema";
import { runAlgorithm } from "./processing.schema";

/** The SDK this page is written against: the plugin's declared operations. */
export type SimpleSdk = QgisSdk<Operations, Streams>;

/**
 * The reference workflow as a page. Every control calls one declared action
 * through the SDK built on the generated schema, and the page keeps only what
 * the host told it: the source layer it opened and the last output it
 * produced. No path is typed here - an export names a file inside the
 * directory the host chose.
 *
 * The centroids control is the other way to run Processing from a page: not a
 * declared action of the plugin, but the host's own `algorithms.run` behind
 * the `algorithms.run` grant, typed by the generated `processing.schema.ts`
 * (`qgis-sdk processing generate`, decision-64).
 */
const PAGE = `
	<h1>Simple</h1>
	<section>
		<button id="open" type="button">Open the fixture dataset</button>
		<output id="source" for="open"></output>
	</section>
	<section>
		<button id="selection" type="button">Selected features</button>
		<output id="selection-result" for="selection"></output>
	</section>
	<section>
		<label>Distance (m) <input id="distance" type="number" value="500" min="0" step="any" /></label>
		<label>Working CRS <input id="crs" type="text" value="EPSG:3857" /></label>
		<button id="buffer" type="button">Buffer</button>
		<output id="buffer-result" for="buffer"></output>
	</section>
	<section>
		<button id="centroids" type="button">Centroids (host Processing)</button>
		<output id="centroids-result" for="centroids"></output>
	</section>
	<section>
		<button id="choose-directory" type="button">Choose the export directory</button>
		<output id="directory" for="choose-directory"></output>
		<label>File name <input id="file-name" type="text" value="buffer.gpkg" /></label>
		<label><input id="overwrite" type="checkbox" /> Overwrite</label>
		<button id="export" type="button">Export the output</button>
		<output id="export-result" for="export"></output>
	</section>
	<p id="error" role="alert"></p>
`;

export interface AppState {
	sourceId: string | null;
	outputId: string | null;
}

/** Render the page into `root`; every button goes through the SDK. */
export function createApp(root: HTMLElement, qgis: SimpleSdk): AppState {
	root.innerHTML = PAGE;
	const state: AppState = { sourceId: null, outputId: null };
	const error = element(root, "error");

	const run = (button: string, work: () => Promise<void>) => {
		element(root, button).addEventListener("click", async () => {
			error.textContent = "";
			try {
				await work();
			} catch (failure: unknown) {
				error.textContent = describe(failure);
			}
		});
	};

	run("open", async () => {
		const layer = await qgis.open_fixture();
		state.sourceId = layer.id;
		element(root, "source").textContent =
			`${layer.name} (${layer.geometry_type}, ${layer.crs ?? "no CRS"})`;
	});

	run("selection", async () => {
		const ids = await qgis.selected_features({
			layer_id: required(state.sourceId, "open the dataset first"),
		});
		element(root, "selection-result").textContent =
			ids.length === 0 ? "nothing selected" : ids.join(", ");
	});

	run("buffer", async () => {
		const output = await qgis.buffer({
			layer_id: required(state.sourceId, "open the dataset first"),
			distance_metres: Number(input(root, "distance").value),
			working_crs: input(root, "crs").value,
		});
		state.outputId = output.id;
		element(root, "buffer-result").textContent =
			`${output.name} (${output.geometry_type}, ${output.crs ?? "no CRS"})`;
	});

	run("centroids", async () => {
		const { outputs } = await runAlgorithm(qgis, "native:centroids", {
			INPUT: required(state.sourceId, "open the dataset first"),
			ALL_PARTS: false,
		});
		const centroids = required(
			outputs.OUTPUT?.id ?? null,
			"the host returned no layer",
		);
		element(root, "centroids-result").textContent =
			`${outputs.OUTPUT?.name} (${outputs.OUTPUT?.geometry_type}) ${centroids}`;
	});

	run("choose-directory", async () => {
		element(root, "directory").textContent =
			await qgis.choose_export_directory();
	});

	run("export", async () => {
		const exported = await qgis.export_layer({
			layer_id: required(state.outputId, "run the buffer first"),
			file_name: input(root, "file-name").value,
			overwrite: input(root, "overwrite").checked,
		});
		element(root, "export-result").textContent =
			`${exported.driver}: ${exported.path}`;
	});

	return state;
}

function required(value: string | null, hint: string): string {
	if (value === null) {
		throw new Error(hint);
	}
	return value;
}

function element(root: HTMLElement, id: string): HTMLElement {
	const found = root.querySelector<HTMLElement>(`#${id}`);
	if (found === null) {
		throw new Error(`the page has no #${id} element`);
	}
	return found;
}

function input(root: HTMLElement, id: string): HTMLInputElement {
	return element(root, id) as HTMLInputElement;
}

function describe(failure: unknown): string {
	return failure instanceof Error ? failure.message : String(failure);
}
