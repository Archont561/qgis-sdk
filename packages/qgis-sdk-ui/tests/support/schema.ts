/**
 * The plugin schema the element tests render against: one `buffer` action
 * with every field kind the catalogue has an element for, so a `qgis-form`
 * exercises the whole catalogue, plus a `log` stream for the log view.
 */

import {
	type BridgeSchema,
	defineBridgeSchema,
	type QgisSdk,
	QgisSdk as Sdk,
} from "@archont561/qgis-sdk";
import type { FileRef, VectorLayerInfo } from "@archont561/qgis-sdk/host";
import {
	createBridgeHarness,
	type HarnessOptions,
	type SchemaBridgeHarness,
} from "@archont561/qgis-sdk/testing";

export type TestHarness = SchemaBridgeHarness<Operations, Streams>;

export interface BufferRequest {
	readonly layer_id: string;
	readonly field_name?: string | null;
	readonly distance_metres: number;
	readonly crs?: string | null;
	readonly mode?: "fast" | "exact";
	readonly output?: FileRef | null;
	readonly folder?: FileRef | null;
	readonly note?: string | null;
	readonly dissolve?: boolean;
	readonly segments?: number;
	readonly colour?: string | null;
}

export interface Operations {
	readonly buffer: {
		readonly request: BufferRequest;
		readonly result: { readonly id: string };
	};
}

export interface LogEvent {
	readonly kind: "data";
	readonly payload: { readonly message: string };
}

export interface Streams {
	readonly log: {
		readonly request: Record<never, never>;
		readonly event: LogEvent;
	};
}

export type TestSdk = QgisSdk<Operations, Streams>;

const FILE_REF = {
	type: "object",
	properties: {
		id: { type: "string" },
		kind: { enum: ["file", "directory"] },
		name: { type: "string" },
	},
	required: ["id", "kind"],
} as const;

export const schema: BridgeSchema<Operations, Streams> = defineBridgeSchema<
	Operations,
	Streams
>({
	schema_version: 1,
	id: "org.example.ui",
	title: "UI fixtures",
	actions: [
		{
			id: "buffer",
			title: "Buffer",
			handler: "buffer",
			request: {
				type: "object",
				properties: {
					layer_id: { type: "string", "x-qgis-sdk": { kind: "layer" } },
					field_name: {
						anyOf: [
							{
								type: "string",
								"x-qgis-sdk": { kind: "field", of: "layer_id" },
							},
							{ type: "null" },
						],
					},
					distance_metres: {
						type: "number",
						minimum: 0,
						"x-qgis-sdk": { kind: "metres" },
					},
					crs: {
						anyOf: [
							{ type: "string", "x-qgis-sdk": { kind: "crs" } },
							{ type: "null" },
						],
					},
					mode: { enum: ["fast", "exact"] },
					output: {
						anyOf: [
							{
								...FILE_REF,
								"x-qgis-sdk": { kind: "file", filters: ["*.gpkg"] },
							},
							{ type: "null" },
						],
					},
					folder: {
						anyOf: [
							{ ...FILE_REF, "x-qgis-sdk": { kind: "directory" } },
							{ type: "null" },
						],
					},
					note: { anyOf: [{ type: "string" }, { type: "null" }] },
					dissolve: { type: "boolean" },
					segments: { type: "integer", minimum: 1, maximum: 64 },
					colour: {
						anyOf: [
							{ type: "string", "x-qgis-sdk": { kind: "colour" } },
							{ type: "null" },
						],
					},
				},
				additionalProperties: false,
				required: ["layer_id", "distance_metres"],
			},
			result: {
				type: "object",
				properties: { id: { type: "string" } },
				required: ["id"],
				additionalProperties: false,
			},
		},
	],
	streams: [
		{
			id: "log",
			title: "Log",
			handler: "log",
			request: { type: "object", properties: {}, additionalProperties: false },
			events: {
				data: {
					type: "object",
					properties: { message: { type: "string" } },
					required: ["message"],
					additionalProperties: false,
				},
			},
		},
	],
});

export const ROADS: VectorLayerInfo = {
	id: "roads-1",
	name: "roads",
	geometry_type: "line",
	crs: "EPSG:2180",
	field_names: ["name", "surface"],
};

export const RIVERS: VectorLayerInfo = {
	id: "rivers-2",
	name: "rivers",
	geometry_type: "line",
	crs: "EPSG:4326",
	field_names: ["name", "length"],
};

/** A harness and the SDK built on it, typed by the fixture schema. */
export function sdkWithHarness(options: HarnessOptions = {}): {
	readonly harness: TestHarness;
	readonly qgis: TestSdk;
} {
	const harness = createBridgeHarness(schema, options);
	const qgis = Sdk.fromBridgeSchema<Operations, Streams>(schema, {
		transport: harness,
	});
	return { harness, qgis };
}

/** Script one `layers.list` reply with these layers. */
export function expectLayers(
	harness: TestHarness,
	layers: readonly VectorLayerInfo[] = [ROADS, RIVERS],
): void {
	harness.expectInvoke("layers.list", () => ({
		items: layers,
		truncated: false,
	}));
}

/** Script one `layers.get` reply with this layer. */
export function expectLayer(
	harness: TestHarness,
	layer: VectorLayerInfo = ROADS,
): void {
	harness.expectInvoke("layers.get", () => layer);
}
