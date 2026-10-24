/**
 * Compile-time half of the generated client (TASK-17 AC 2).
 *
 * This file is never executed: `tsc --noEmit` over `tests` is the assertion. Each
 * `@ts-expect-error` fails the build if the line below it stops being an error,
 * so a generator that loosened the types would have to delete the comment too.
 */
import type { BridgeClient } from "../src/bridge";
import {
	type BridgeClientLike,
	createOperations,
	OPERATIONS,
	type OperationId,
	type PluginOperations,
	type SitesWatchEvent,
	type StreamHandle,
} from "./contracts/generated/clients/sites";

declare const client: BridgeClientLike;
const operations: PluginOperations = createOperations(client);
void operations;

// The hand-written kernel is a client the generated module accepts as it is:
// nothing has to be adapted between `BridgeClient` and the generated surface.
declare const kernel: BridgeClient;
const kernelAccepted: BridgeClientLike = kernel;
void kernelAccepted;

// An operation id is one of the declared literals, so a typo is a type error.
const summaryId: OperationId = "sites.summary";
void summaryId;
void OPERATIONS;

// @ts-expect-error `sites.relfresh` is not a declared operation id.
const misspelledId: OperationId = "sites.relfresh";
void misspelledId;

// There is no generic escape hatch to assert a type by hand: the map is the
// public guarantee, and `invoke` stays private to the generated module.
// @ts-expect-error The generated map exposes operations, not a generic invoke.
void operations.invoke;

// A misspelled operation is not a member of the map.
// @ts-expect-error `sites.relfresh` does not exist.
void operations.sites.relfresh;

// A generated method takes one declared request, not a bare string.
// @ts-expect-error The request is an object, not a layer id.
void operations.sites.summary("sites");

// A required input cannot be dropped just because it is an object.
// @ts-expect-error `layer_id` is required by the declaration.
void operations.sites.details({ options: { limit: 1 } });

// An unknown argument is rejected at the call site, not at runtime only.
void operations.sites.summary({
	layer_id: "sites",
	// @ts-expect-error `guess` is not a declared argument.
	guess: true,
});

// A declared argument keeps its type.
void operations.sites.summary({
	// @ts-expect-error `limit` is an integer bounded by the schema, never a string.
	limit: "10",
	layer_id: "sites",
});

// An enum argument is one of the declared literals.
void operations.sites.summary({
	layer_id: "sites",
	// @ts-expect-error `slow` is not a declared literal.
	mode: "slow",
});

// -- streams (decision-28) -----------------------------------------------------

// A stream id is an operation id like any other.
const watchId: OperationId = "sites.watch";
void watchId;

// A stream member resolves with a handle, not with a result.
const opened: Promise<StreamHandle> = operations.sites.watch(
	{ layer_id: "roads" },
	{},
);
void opened;

// The event handler is typed by the stream's own union, narrowed by kind.
void operations.sites.watch(
	{ layer_id: "roads" },
	{
		onEvent: (event: SitesWatchEvent) => {
			if (event.kind === "data") {
				const change: "added" | "removed" | "modified" = event.payload.change;
				void change;
				// @ts-expect-error `done` belongs to a progress payload, not a data one.
				void event.payload.done;
			} else {
				const done: number = event.payload.done;
				void done;
			}
			// @ts-expect-error `state` is not an event kind this stream declared.
			if (event.kind === "state") {
				void event;
			}
		},
		onTerminal: (terminal) => {
			const kind: "complete" | "error" | "cancelled" | "gap" | "disposed" =
				terminal.kind;
			void kind;
		},
	},
);

// A stream request is as strict as an action request.
void operations.sites.watch(
	{
		layer_id: "roads",
		// @ts-expect-error `guess` is not a declared argument.
		guess: true,
	},
	{},
);

// @ts-expect-error The handlers are required; a stream without a listener is a leak.
void operations.sites.watch({ layer_id: "roads" });

// @ts-expect-error A stream is not invoked like an action: there is no result to await.
void operations.sites.watch({ layer_id: "roads" }).then((value) => value.total);
