/**
 * The framework-free store core (decision-47).
 *
 * Every adapter - `./react`, `./vue`, `./svelte`, or a vanilla page with no
 * adapter at all - drives the same four stores. A store is a value plus the
 * Svelte store contract: `subscribe(listener)` calls the listener at once with
 * the current snapshot and again after every change, and returns the
 * unsubscribe function; `getSnapshot()` is the same value without a
 * subscription, kept referentially stable between changes so React's
 * `useSyncExternalStore` can compare it. Nothing in this module imports a
 * framework, touches the DOM or runs at import time.
 *
 * - {@link OperationStore} runs one generated operation: the latest run wins,
 *   an aborted call is swallowed, and `run` never rejects into a handler.
 * - {@link StreamStore} holds one generated stream open while its input is
 *   non-null, reopening only when the input's *content* changes.
 * - {@link FormStore} binds the values of one declared action's request to its
 *   schema: fields from the declaration, issues from the validator, submission
 *   through an operation store.
 * - {@link HostQueryStore} reads the curated host surface and says `refused`
 *   - before any call leaves the page - when the view was not granted the
 *   operation it needs.
 */

export type { Store, StoreListener } from "./stores/base";
export { QgisSdkStoreError } from "./stores/base";
export type {
	FormField,
	FormFieldKind,
	FormOptions,
	FormState,
	FormValues,
} from "./stores/form";
export { FormStore, formStore, labelFor, schemaFields } from "./stores/form";
export type {
	HostQueryLoader,
	HostQueryState,
	LayersQueryOptions,
} from "./stores/host-query";
export {
	HostQueryStore,
	layerFieldsQuery,
	layersQuery,
} from "./stores/host-query";
export type { Operation, OperationState } from "./stores/operation";
export { OperationStore } from "./stores/operation";
export type {
	Stream,
	StreamHandleLike,
	StreamHandlersLike,
	StreamState,
	StreamTerminalLike,
} from "./stores/stream";
export { StreamStore, stableKey } from "./stores/stream";
