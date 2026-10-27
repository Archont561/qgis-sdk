/**
 * Processing from a page (decision-64): the value aliases a generated
 * `processing.schema.ts` annotates with, and `runAlgorithm`, which sends one
 * `algorithms.run` and reshapes the tagged outputs into the result object the
 * generated `<Provider><Algorithm>Result` type spells.
 *
 * The typing lives in the generated module, not here: `qgis-sdk processing
 * generate` emits an `AlgorithmRegistry` for the providers the project asked
 * for and a `runAlgorithm` bound to it. This module is generic over any such
 * registry so the bridge itself ships no catalogue (decision-47: zero runtime
 * data that goes stale with a QGIS release).
 *
 * The host validates the parameters against the algorithm's own description
 * before anything runs; a layer input is an owned layer id, a file input is a
 * ref the host minted for this view, and an omitted destination comes back as
 * an owned layer or a readable ref.
 */

import type {
	FileRef,
	HostInvokeOptions,
	HostOperations,
	RunOutput,
	RunResult,
	VectorLayerInfo,
} from "./generated/host";

export type {
	AlgorithmInfo,
	AlgorithmSummary,
	FileRef,
	HostInvokeOptions,
	OutputInfo,
	ParameterInfo,
	ProviderInfo,
	RunOutput,
	RunResult,
	VectorLayerInfo,
} from "./generated/host";

/** A layer input: the id of a layer the host owns, or a ref the view holds. */
export type LayerRef = string | FileRef;
/** Where an output goes: a writable ref, or `null` to let the host allocate one. */
export type Destination = FileRef | null;
/** `"xmin,xmax,ymin,ymax [crs]"` as QGIS writes it, or the four numbers. */
export type Extent = string | readonly [number, number, number, number];
/** `"x,y [crs]"` or the two numbers. */
export type PointValue = string | readonly [number, number];
/** `[lower, upper]`. */
export type RangeValue = readonly [number, number];

/**
 * What a generated `AlgorithmRegistry` is: params and result per algorithm id.
 * Spelled as a mapped constraint over the registry itself so an `interface`
 * (which has no implicit index signature) satisfies it.
 */
export type AlgorithmRegistryLike<R> = {
	readonly [K in keyof R]: { readonly params: object; readonly result: object };
};

/** The part of a `QgisSdk` (or anything else) `runAlgorithm` needs. */
export interface AlgorithmHost {
	readonly host: Pick<HostOperations, "algorithms">;
}

/** One run as the page sees it: the outputs by name, plus the reply as it crossed. */
export interface AlgorithmRun<Result extends object> {
	readonly algorithm: string;
	readonly outputs: Result;
	readonly raw: RunResult;
}

/**
 * Run `id` with `params` through `qgis.host.algorithms.run` and reshape the
 * reply: a `vector` output becomes its `VectorLayerInfo`, a `file` output its
 * `FileRef`, a `value` output the scalar - keyed by output name, which is what
 * the generated `...Result` interfaces declare.
 *
 * Both type parameters are meant to be bound by the generated module's own
 * `runAlgorithm`; calling this one directly needs them spelled out.
 */
export async function runAlgorithm<
	R extends AlgorithmRegistryLike<R>,
	K extends keyof R & string,
>(
	qgis: AlgorithmHost,
	id: K,
	params: R[K]["params"],
	options?: HostInvokeOptions,
): Promise<AlgorithmRun<R[K]["result"]>> {
	const raw = await qgis.host.algorithms.run(
		{ algorithm_id: id, params: params as Record<string, unknown> },
		options,
	);
	return {
		algorithm: raw.algorithm,
		outputs: outputsByName(raw.outputs) as R[K]["result"],
		raw,
	};
}

/** Unwrap a tagged output list into `{ [name]: layer | ref | value }`. */
export function outputsByName(
	outputs: readonly RunOutput[],
): Record<
	string,
	VectorLayerInfo | FileRef | string | number | boolean | null | undefined
> {
	const result: Record<
		string,
		VectorLayerInfo | FileRef | string | number | boolean | null | undefined
	> = {};
	for (const output of outputs) {
		if (output.kind === "vector") result[output.name] = output.layer;
		else if (output.kind === "file") result[output.name] = output.file;
		else result[output.name] = output.value;
	}
	return result;
}
