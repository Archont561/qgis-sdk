/**
 * Thin Svelte 5 bindings over the store core (TASK-69, decision-47).
 *
 * This entry point is optional and is the only one that imports Svelte. The
 * stores in `./stores` already satisfy Svelte's store contract - `subscribe`
 * calls at once and on every change and returns the unsubscriber - so a
 * component writes `$state` over any of them with no wrapper. What this
 * module adds is the little Svelte asks for around that:
 *
 * - `setQgisSdk`/`getQgisSdk`, one `QgisSdk` through component context;
 * - factories that tie a store's lifetime to the component that made it
 *   (`onDestroy` aborts a call, closes a stream, disposes a form), which a
 *   bare `new OperationStore(...)` in a `<script>` would not;
 * - `toRune`, a `$state`-friendly `{ current }` over any store, through
 *   `fromStore` of `svelte/store`, for a component that prefers runes.
 */

import { getContext, onDestroy, setContext } from "svelte";
import { fromStore } from "svelte/store";
import { QgisSdkError } from "./errors";
import type { QgisSdk, QgisSdkCore } from "./qgis-sdk";
import type { OperationMap, StreamMap } from "./schema";
import {
	type FormOptions,
	FormStore,
	type HostQueryStore,
	type Operation,
	OperationStore,
	type Store,
	type Stream,
	type StreamHandlersLike,
	StreamStore,
} from "./stores";

export type {
	Operation,
	OperationState,
	Stream,
	StreamHandleLike,
	StreamHandlersLike,
	StreamState,
	StreamTerminalLike,
} from "./stores";

/** A helper was used outside the shape it needs. */
export class QgisSdkBridgeSvelteError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "svelte_binding");
	}
}

/** The context key `setQgisSdk` writes and `getQgisSdk` reads. */
export const QGIS_SDK_CONTEXT: unique symbol = Symbol("qgis-sdk");

/**
 * Share a `QgisSdk` with the component subtree; call during component
 * initialisation. The SDK is shared as given and never closed here.
 */
export function setQgisSdk<T extends QgisSdkCore<unknown, unknown>>(
	qgis: T,
): T {
	setContext(QGIS_SDK_CONTEXT, qgis);
	return qgis;
}

/**
 * The `QgisSdk` the nearest `setQgisSdk` shared.
 *
 * The type parameters name the generated `Operations` and `Streams`; they are
 * the caller's claim, the same way the ancestor's argument was the page's.
 */
export function getQgisSdk<O = OperationMap, S = StreamMap>(): QgisSdk<O, S> {
	const qgis = getContext<QgisSdkCore<unknown, unknown> | undefined>(
		QGIS_SDK_CONTEXT,
	);
	if (qgis === undefined) {
		throw new QgisSdkBridgeSvelteError(
			"getQgisSdk needs setQgisSdk in an ancestor component",
		);
	}
	return qgis as unknown as QgisSdk<O, S>;
}

/**
 * An operation store whose in-flight call is aborted when the component is
 * destroyed; read it as `$op` or pass it to {@link toRune}.
 */
export function operation<I, R>(
	operation: Operation<I, R>,
): OperationStore<I, R> {
	const store = new OperationStore(operation);
	onDestroy(store.abort);
	return store;
}

/**
 * A stream store closed when the component is destroyed. Pass the input now
 * or later with `store.setInput(...)`; `$effect(() => store.setInput(input))`
 * follows a reactive one, by content.
 */
export function stream<I, E>(
	open: Stream<I, E>,
	input: I | null = null,
	handlers: StreamHandlersLike<E> = {},
): StreamStore<I, E> {
	const store = new StreamStore(open, handlers);
	store.setInput(input);
	onDestroy(store.close);
	return store;
}

type RequestOf<O, K extends keyof O> = O[K] extends {
	readonly request: infer Req;
}
	? Req
	: never;
type ResultOf<O, K extends keyof O> = O[K] extends {
	readonly result: infer Res;
}
	? Res
	: never;

/**
 * The form of one declared action, disposed with the component: render
 * `form.fields`, bind `$form.values`, call `form.submit()`.
 */
export function form<O, K extends keyof O & string>(
	qgis: QgisSdkCore<O, unknown>,
	id: K,
	options?: FormOptions,
): FormStore<RequestOf<O, K> & object, ResultOf<O, K>> {
	const store = new FormStore<RequestOf<O, K> & object, ResultOf<O, K>>(
		qgis as QgisSdkCore<unknown, unknown>,
		id,
		options,
	);
	onDestroy(() => store.dispose());
	return store;
}

/**
 * A host query store refreshed now (unless `auto` is `false`) and aborted
 * when the component is destroyed: `hostQuery(layersQuery(qgis))`.
 */
export function hostQuery<T>(
	store: HostQueryStore<T>,
	options: { readonly auto?: boolean } = {},
): HostQueryStore<T> {
	if (options.auto !== false) {
		void store.refresh();
	}
	onDestroy(store.abort);
	return store;
}

/** A runes-friendly view of any store: `const op = toRune(store); op.current`. */
export function toRune<T>(store: Store<T>): { readonly current: T } {
	return fromStore(store);
}
