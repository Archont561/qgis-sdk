/**
 * Thin Vue 3 bindings over the store core (decision-47).
 *
 * This entry point is optional and is the only one that imports Vue. It adds
 * no behaviour: every composable wraps one store from `./stores` in a
 * `shallowRef` that follows the store's snapshots and stops following when
 * the effect scope that created it is disposed. The composables take the
 * methods a `QgisSdk` already has - `qgis.sites.summary`, `qgis.sites.watch`
 * - so the typed contract is the generated one, not a Vue copy of it.
 *
 * `provideQgisSdk(qgis)` in `setup()` of an ancestor shares one `QgisSdk`
 * with a subtree; `useQgisSdk()` hands it back under the page's types. The
 * provider never closes what it was given.
 */

import {
	type InjectionKey,
	inject,
	type MaybeRefOrGetter,
	onScopeDispose,
	provide,
	type ShallowRef,
	shallowRef,
	toValue,
	watch,
} from "vue";
import { QgisSdkError } from "./errors";
import type { QgisSdk, QgisSdkCore } from "./qgis-sdk";
import type { OperationMap, StreamMap } from "./schema";
import {
	type FormOptions,
	type FormState,
	FormStore,
	type HostQueryState,
	type HostQueryStore,
	type Operation,
	type OperationState,
	OperationStore,
	type Store,
	type Stream,
	type StreamHandlersLike,
	type StreamState,
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

/** A composable was used outside the shape it needs. */
export class QgisSdkBridgeVueError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "vue_binding");
	}
}

/** The injection key `provideQgisSdk` writes and `useQgisSdk` reads. */
export const QGIS_SDK_KEY: InjectionKey<QgisSdkCore<unknown, unknown>> =
	Symbol("qgis-sdk");

/**
 * Share a `QgisSdk` with the component subtree; call in `setup()`.
 *
 * The SDK is shared as given, whatever its schema, and never closed here:
 * the page that built it closes it.
 */
export function provideQgisSdk(qgis: QgisSdkCore<unknown, unknown>): void {
	provide(QGIS_SDK_KEY, qgis);
}

/**
 * The `QgisSdk` the nearest `provideQgisSdk` shared.
 *
 * The type parameters name the generated `Operations` and `Streams`; they are
 * the caller's claim, the same way the provider's argument was the page's.
 */
export function useQgisSdk<O = OperationMap, S = StreamMap>(): QgisSdk<O, S> {
	// Outside `setup()` Vue warns and returns undefined; inside, the default.
	const qgis = inject(QGIS_SDK_KEY, null) ?? null;
	if (qgis === null) {
		throw new QgisSdkBridgeVueError(
			"useQgisSdk needs provideQgisSdk in an ancestor's setup()",
		);
	}
	return qgis as unknown as QgisSdk<O, S>;
}

/**
 * Follow any store as a shallow ref; the subscription ends with the scope.
 */
export function useStore<T>(store: Store<T>): Readonly<ShallowRef<T>> {
	const state = shallowRef(store.getSnapshot());
	const stop = store.subscribe((snapshot) => {
		state.value = snapshot;
	});
	onScopeDispose(stop);
	return state;
}

/** What {@link useOperation} returns. */
export interface UseOperation<I, R> {
	readonly state: Readonly<ShallowRef<OperationState<R>>>;
	/** Resolves with the value, or `undefined` when the state carries why not. */
	run(input: I): Promise<R | undefined>;
	/** Abort the in-flight call locally; the host may still run it. */
	abort(): void;
	/** Back to `idle`, aborting anything in flight. */
	reset(): void;
	readonly store: OperationStore<I, R>;
}

/**
 * Run a generated operation from a component; disposing the scope aborts
 * whatever is in flight.
 */
export function useOperation<I, R>(
	operation: Operation<I, R>,
): UseOperation<I, R> {
	const store = new OperationStore(operation);
	onScopeDispose(store.abort);
	return {
		state: useStore(store),
		run: store.run,
		abort: store.abort,
		reset: store.reset,
		store,
	};
}

/** A value, a ref or a getter: what `useStream` accepts as its input. */
export type StreamInput<I> = MaybeRefOrGetter<I | null>;

/**
 * Hold a generated stream open while the scope lives.
 *
 * `input` may be a value, a ref or a getter; the subscription follows its
 * *content* - a new object with the same fields reopens nothing, a different
 * one closes and reopens, `null` closes. Disposing the scope closes the
 * stream, even before the host acknowledged it.
 */
export function useStream<I, E>(
	open: Stream<I, E>,
	input: StreamInput<I>,
	handlers: StreamHandlersLike<E> = {},
): Readonly<ShallowRef<StreamState<E>>> & {
	readonly store: StreamStore<I, E>;
} {
	const store = new StreamStore(open, handlers);
	const state = useStore(store);
	watch(
		() => toValue(input),
		(value) => store.setInput(value),
		{
			immediate: true,
			deep: true,
		},
	);
	onScopeDispose(store.close);
	return Object.assign(state, { store });
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
 * The form of one declared action: `qgis.<id>` with its fields, values,
 * issues and submission; disposing the scope aborts a submission in flight.
 */
export function useForm<O, K extends keyof O & string>(
	qgis: QgisSdkCore<O, unknown>,
	id: K,
	options?: FormOptions,
): {
	readonly state: Readonly<ShallowRef<FormState<ResultOf<O, K>>>>;
	readonly form: FormStore<RequestOf<O, K> & object, ResultOf<O, K>>;
} {
	const form = new FormStore<RequestOf<O, K> & object, ResultOf<O, K>>(
		qgis as QgisSdkCore<unknown, unknown>,
		id,
		options,
	);
	onScopeDispose(() => form.dispose());
	return { state: useStore(form), form };
}

/**
 * Follow a host query store: `useHostQuery(layersQuery(qgis))` for a layer
 * picker. `refresh` runs at once unless `auto` is `false`; disposing the
 * scope aborts a load in flight.
 */
export function useHostQuery<T>(
	store: HostQueryStore<T>,
	options: { readonly auto?: boolean } = {},
): {
	readonly state: Readonly<ShallowRef<HostQueryState<T>>>;
	readonly query: HostQueryStore<T>;
} {
	const state = useStore(store);
	if (options.auto !== false) {
		void store.refresh();
	}
	onScopeDispose(store.abort);
	return { state, query: store };
}
