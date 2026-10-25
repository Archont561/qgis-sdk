import type { PluginOperations } from "./bridge";

/**
 * The reference workflow as a page. Every control calls one declared action
 * through the generated client, and the page keeps only what the host told
 * it: the source layer it opened and the last output it produced. No path is
 * typed here - an export names a file inside the directory the host chose.
 */
const PAGE = `
	<h1>Reference workflow</h1>
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

/** Render the page into `root`; every button goes through the generated client. */
export function createApp(
	root: HTMLElement,
	operations: PluginOperations,
): AppState {
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
		const layer = await operations.open_fixture();
		state.sourceId = layer.id;
		element(root, "source").textContent =
			`${layer.name} (${layer.geometry_type}, ${layer.crs ?? "no CRS"})`;
	});

	run("selection", async () => {
		const ids = await operations.selected_features({
			layer_id: required(state.sourceId, "open the dataset first"),
		});
		element(root, "selection-result").textContent =
			ids.length === 0 ? "nothing selected" : ids.join(", ");
	});

	run("buffer", async () => {
		const output = await operations.buffer({
			layer_id: required(state.sourceId, "open the dataset first"),
			distance_metres: Number(input(root, "distance").value),
			working_crs: input(root, "crs").value,
		});
		state.outputId = output.id;
		element(root, "buffer-result").textContent =
			`${output.name} (${output.geometry_type}, ${output.crs ?? "no CRS"})`;
	});

	run("choose-directory", async () => {
		element(root, "directory").textContent =
			await operations.choose_export_directory();
	});

	run("export", async () => {
		const exported = await operations.export_layer({
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
