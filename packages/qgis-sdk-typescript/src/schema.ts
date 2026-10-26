/**
 * The bridge schema: a plugin description that also carries its types.
 *
 * `qgis-sdk bridge generate` writes one `bridge.schema.ts` per plugin
 * (decision-44). That module has no code of its own: it declares the value
 * interfaces, two maps - `Operations` and `Streams`, keyed by operation id -
 * and ends in `defineBridgeSchema<Operations, Streams>({ ...description })`.
 * The two type parameters never exist at run time; they ride on the returned
 * object so `QgisSdk.fromBridgeSchema(schema)` can infer them, and the
 * description itself is what the SDK validates against.
 */

import { type PluginDescription, parsePluginDescription } from "./declarations";

/** What one declared action promises: an object in, a value out. */
export interface OperationShape {
	readonly request: object;
	readonly result: unknown;
}

/** What one declared stream promises: an object in, discriminated events out. */
export interface StreamShape {
	readonly request: object;
	readonly event: { readonly kind: string; readonly payload: unknown };
}

/** The default, untyped map: any id, any shape. */
export type OperationMap = { readonly [id: string]: OperationShape };

/** The default, untyped map: any id, any shape. */
export type StreamMap = { readonly [id: string]: StreamShape };

/**
 * A parsed plugin description carrying its `Operations` and `Streams` types.
 *
 * The `"~types"` member is compile-time only: it is never set, and a schema is
 * a frozen {@link PluginDescription} and nothing more at run time. It is a
 * string key, not a unique symbol, so the type stays structurally the same
 * across the package's entry points.
 */
export interface BridgeSchema<O = OperationMap, S = StreamMap>
	extends PluginDescription {
	readonly "~types"?: {
		readonly operations: O;
		readonly streams: S;
	};
}

/** The `Operations` map a schema carries. */
export type OperationsOf<Schema> =
	Schema extends BridgeSchema<infer O, unknown> ? O : never;

/** The `Streams` map a schema carries. */
export type StreamsOf<Schema> =
	Schema extends BridgeSchema<unknown, infer S> ? S : never;

/**
 * Parse a description and type it; the generated module is the only caller.
 *
 * The description is checked the way any description is (`schema_version`,
 * ids, handlers, declared streams), so a hand-edited or stale module fails
 * here, at import, rather than on the first call.
 */
export function defineBridgeSchema<
	O extends Record<keyof O, OperationShape>,
	S extends Record<keyof S, StreamShape>,
>(input: string | Readonly<Record<string, unknown>>): BridgeSchema<O, S> {
	return parsePluginDescription(input) as BridgeSchema<O, S>;
}
