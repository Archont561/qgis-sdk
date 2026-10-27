import { expect, test } from "@archont561/bun-test-utils";
import {
	type AlgorithmHost,
	type Destination,
	type LayerRef,
	outputsByName,
	runAlgorithm,
} from "@";
import {
	createHost,
	type FileRef,
	type HostClientLike,
	type HostInvokeOptions,
	type RunResult,
	type VectorLayerInfo,
} from "@/host";

// What `qgis-sdk processing generate` emits for one algorithm, by hand.
interface NativeBufferParams {
	INPUT: LayerRef;
	DISTANCE?: number;
	OUTPUT?: Destination;
}
interface NativeBufferResult {
	OUTPUT?: VectorLayerInfo;
}
interface NativeStatsResult {
	COUNT?: number;
	OUTPUT_HTML_FILE?: FileRef;
}
interface Registry {
	readonly "native:buffer": {
		params: NativeBufferParams;
		result: NativeBufferResult;
	};
	readonly "native:basicstatisticsforfields": {
		params: { INPUT_LAYER: LayerRef; FIELD_NAME: string };
		result: NativeStatsResult;
	};
}

const layer: VectorLayerInfo = {
	id: "layer-9",
	name: "buffered",
	geometry_type: "polygon",
	field_names: ["id"],
	crs: "EPSG:3857",
};
const report: FileRef = {
	kind: "file",
	id: "abcdef0123456789",
	name: "report.html",
	operations: ["read"],
};

function scripted(reply: RunResult): {
	readonly qgis: AlgorithmHost;
	readonly sent: {
		operation: string;
		payload: unknown;
		options: HostInvokeOptions | undefined;
	}[];
} {
	const sent: {
		operation: string;
		payload: unknown;
		options: HostInvokeOptions | undefined;
	}[] = [];
	const client: HostClientLike = {
		invoke: (operation, payload, options) => {
			sent.push({ operation, payload, options });
			return Promise.resolve(reply);
		},
		subscribe: () => Promise.reject(new Error("not a stream")),
	};
	return { qgis: { host: createHost(client) }, sent };
}

test("runAlgorithm sends one algorithms.run and keys the outputs by name", async () => {
	const { qgis, sent } = scripted({
		algorithm: "native:buffer",
		outputs: [{ name: "OUTPUT", kind: "vector", layer }],
	});

	const run = await runAlgorithm<Registry, "native:buffer">(
		qgis,
		"native:buffer",
		{ INPUT: "layer-1", DISTANCE: 25 },
		{ signal: AbortSignal.timeout(5000) },
	);

	expect(sent).toHaveLength(1);
	expect(sent[0]?.operation).toBe("algorithms.run");
	expect(sent[0]?.payload).toEqual({
		algorithm_id: "native:buffer",
		params: { INPUT: "layer-1", DISTANCE: 25 },
	});
	expect(sent[0]?.options?.signal).toBeInstanceOf(AbortSignal);
	expect(run.algorithm).toBe("native:buffer");
	expect(run.outputs.OUTPUT).toEqual(layer);
	expect(run.raw.outputs).toHaveLength(1);
	// The typed result is what the generated interface declares.
	const typed: NativeBufferResult = run.outputs;
	expect(typed.OUTPUT?.geometry_type).toBe("polygon");
});

test("file and scalar outputs come back as the ref and the value", async () => {
	const { qgis } = scripted({
		algorithm: "native:basicstatisticsforfields",
		outputs: [
			{ name: "COUNT", kind: "value", value: 3 },
			{ name: "OUTPUT_HTML_FILE", kind: "file", file: report },
			{ name: "EMPTY", kind: "value", value: null },
		],
	});

	const run = await runAlgorithm<Registry, "native:basicstatisticsforfields">(
		qgis,
		"native:basicstatisticsforfields",
		{ INPUT_LAYER: "layer-1", FIELD_NAME: "id" },
	);

	expect(run.outputs.COUNT).toBe(3);
	expect(run.outputs.OUTPUT_HTML_FILE).toEqual(report);
	expect(outputsByName(run.raw.outputs)).toEqual({
		COUNT: 3,
		OUTPUT_HTML_FILE: report,
		EMPTY: null,
	});
});

test("a reply that is not a run result is a contract error, not a shape", async () => {
	const { qgis } = scripted({
		algorithm: "native:buffer",
	} as unknown as RunResult);

	await expect(
		runAlgorithm<Registry, "native:buffer">(qgis, "native:buffer", {
			INPUT: "layer-1",
		}),
	).rejects.toMatchObject({ code: "contract_validation_failed" });
});
