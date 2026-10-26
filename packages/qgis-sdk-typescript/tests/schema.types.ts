/**
 * Compile-time half of `QgisSdk.fromBridgeSchema` (TASK-66 AC #2).
 *
 * This file is never executed: `tsc --noEmit` over `tests` is the assertion.
 * Each `@ts-expect-error` fails the build if the line below it stops being an
 * error, so a schema module or an SDK type that loosened would have to delete
 * the comment too.
 */
import type { BridgeClient } from "../src/bridge";
import type { HostOperationId, HostOperations } from "../src/generated/host";
import { QgisSdk, type StreamHandle } from "../src/qgis-sdk";
import type { BridgeSchema, OperationsOf, StreamsOf } from "../src/schema";
import { createBridgeHarness } from "../src/testing";
import schema, {
	type Operations,
	type SitesSummaryResult,
	type SitesWatchEvent,
	type Streams,
} from "./contracts/generated/clients/sites.schema";

// The generated default export carries both maps; the SDK infers them.
const typed: BridgeSchema<Operations, Streams> = schema;
void typed;
type InferredOperations = OperationsOf<typeof schema>;
const inferred: InferredOperations = {} as Operations;
void inferred;
const streams: StreamsOf<typeof schema> = {} as Streams;
void streams;

const qgis = QgisSdk.fromBridgeSchema(schema, {
	transport: createBridgeHarness(schema),
});

// A declared action is a method named by its id; the result is the declared one.
const summary: Promise<SitesSummaryResult> = qgis["sites.summary"]({
	layer_id: "sites",
});
void summary;
async function total(): Promise<number> {
	const result = await qgis["sites.summary"]({
		layer_id: "sites",
		mode: "exact",
	});
	return result.total;
}
void total;

// An empty request may be omitted; a nonempty one may not.
void qgis["sites.refresh"]();
// @ts-expect-error `layer_id` is required by the declaration.
void qgis["sites.summary"]();
// @ts-expect-error `layer_id` is required by the declaration.
void qgis["sites.details"]({ options: { limit: 1 } });

// A wrong argument shape is a compile error.
// @ts-expect-error The request is an object, not a layer id.
void qgis["sites.summary"]("sites");
void qgis["sites.summary"]({
	layer_id: "sites",
	// @ts-expect-error `guess` is not a declared argument.
	guess: true,
});
// @ts-expect-error `mode` is a Literal of two values.
void qgis["sites.summary"]({ layer_id: "sites", mode: "slow" });
// @ts-expect-error `limit` is an integer, not a string.
void qgis["sites.details"]({ layer_id: "sites", options: { limit: "1" } });

// An unknown operation is not a member.
// @ts-expect-error `sites.relfresh` is not declared.
void qgis["sites.relfresh"];

// A result is read as declared, not as `unknown`.
async function wrongField(): Promise<void> {
	const result = await qgis["sites.summary"]({ layer_id: "sites" });
	// @ts-expect-error `largest_site` is not a declared result field.
	void result.largest_site;
}
void wrongField;

// A stream takes its request and typed handlers, and resolves with a handle.
const watching: Promise<StreamHandle> = qgis["sites.watch"](
	{ layer_id: "sites" },
	{
		onEvent: (event: SitesWatchEvent) => {
			if (event.kind === "data") {
				const change: "added" | "removed" | "modified" = event.payload.change;
				void change;
			} else {
				const done: number = event.payload.done;
				void done;
			}
		},
	},
);
void watching;
// @ts-expect-error A stream needs its handlers.
void qgis["sites.watch"]({ layer_id: "sites" });
void qgis["sites.watch"](
	{ layer_id: "sites" },
	{
		// @ts-expect-error `state` is not an event `sites.watch` declares.
		onEvent: (event: { kind: "state" }) => void event,
	},
);

// The core members keep their types.
const client: BridgeClient = qgis.client;
void client;
const host: HostOperations = qgis.host;
void host;
const granted: readonly HostOperationId[] = qgis.host.granted;
void granted;
const ready: Promise<void> = qgis.ready;
void ready;
qgis.close();

// The typed harness: a payload is the declared request, a reply the declared result.
const harness = createBridgeHarness(schema);
harness.expectInvoke("sites.summary", (payload) => {
	const layer: string = payload.layer_id;
	void layer;
	return { total: 1, largest: layer, mode: "fast" };
});
// @ts-expect-error The reply must be the declared result.
harness.expectInvoke("sites.summary", () => ({ total: "1" }));
// @ts-expect-error `sites.relfresh` is not declared.
harness.expectInvoke("sites.relfresh", () => null);
harness.expectSubscribe("sites.watch", (payload) => {
	const layer: string = payload.layer_id;
	void layer;
});
// A host id is accepted too, loosely typed.
harness.expectInvoke("layers.list", () => ({ items: [], truncated: false }));
