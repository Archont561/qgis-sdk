/**
 * Compile-time half of the generated client (TASK-17 AC 2).
 *
 * This file is never executed: `tsc --noEmit` over `tests` is the assertion. Each
 * `@ts-expect-error` fails the build if the line below it stops being an error,
 * so a generator that loosened the types would have to delete the comment too.
 */
import {
	type BridgeClientLike,
	createOperations,
	OPERATIONS,
	type OperationId,
	type PluginOperations,
} from "./contracts/generated/clients/sites";

declare const client: BridgeClientLike;
const operations: PluginOperations = createOperations(client);
void operations;

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
