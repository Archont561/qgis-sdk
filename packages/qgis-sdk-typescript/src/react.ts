/**
 * Thin React bindings over the store core (decision-18, decision-47).
 *
 * This entry point is optional and is the only one that imports React. It adds
 * no second client: a component reaches the same `QgisSdk` or `BridgeClient` a
 * vanilla page would build, through a provider that is handed a `QgisSdk`
 * (and leaves it alone), is handed a client (same), or owns a client built on
 * a transport (and closes it on unmount). The hooks take the methods a
 * `QgisSdk` already has - `qgis.sites.summary`, `qgis.sites.watch` - so
 * the typed contract is the generated one, not a React copy of it.
 *
 * The behaviour lives in `./stores`: `useOperation` is an `OperationStore`
 * read through `useSyncExternalStore`, `useStream` a `StreamStore`, `useForm`
 * a `FormStore` and `useHostQuery` a `HostQueryStore`. What the hooks add is
 * lifetime: a call aborted when its component unmounts, a stream closed on
 * unmount or when its input changes, and a simulated StrictMode remount that
 * leaves exactly one of each.
 */

import {
	createContext,
	createElement,
	type ReactElement,
	type ReactNode,
	useContext,
	useEffect,
	useMemo,
	useState,
	useSyncExternalStore,
} from "react";
import {
	BridgeClient,
	type BridgeClientOptions,
	type WireTransport,
} from "./bridge";
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

/** A hook or provider was used outside the shape it needs. */
export class QgisSdkBridgeReactError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "react_binding");
	}
}

interface Shared {
	readonly client: BridgeClient;
	readonly qgis: QgisSdkCore<unknown, unknown> | null;
}

const ClientContext = createContext<Shared | null>(null);

/** Props for {@link BridgeProvider}: exactly one of `qgis`, `client` or `transport`. */
export interface BridgeProviderProps {
	/**
	 * A `QgisSdk` the page built, whatever its schema; the provider shares it
	 * and never closes it. `useQgisSdk` hands it back under the page's types.
	 */
	readonly qgis?: QgisSdkCore<unknown, unknown>;
	/** A client the caller owns; the provider never closes it. */
	readonly client?: BridgeClient;
	/** A transport the provider builds and owns a client for. */
	readonly transport?: WireTransport;
	/** Options for the owned client; ignored when `client` is given. */
	readonly options?: BridgeClientOptions;
	readonly children?: ReactNode;
}

/**
 * Share one client with a subtree.
 *
 * An owned client is created in an effect, never during render, because
 * StrictMode renders twice and a client made in render would leave a second
 * listener on the transport. Until that effect has run the subtree is not
 * rendered, which is one tick. StrictMode's simulated unmount closes the
 * owned client and the effect that follows makes a new one, so the subtree
 * never holds a dead client. The transport must be stable across renders; to
 * swap it, change the provider's `key`.
 */
export function BridgeProvider(props: BridgeProviderProps): ReactElement {
	const { qgis, client, transport, options, children } = props;
	const given = [qgis, client, transport].filter(
		(source) => source !== undefined,
	).length;
	if (given !== 1) {
		throw new QgisSdkBridgeReactError(
			"BridgeProvider needs exactly one of qgis, client or transport",
		);
	}
	const timeoutMs = options?.timeoutMs;
	const [owned, setOwned] = useState<BridgeClient | null>(null);
	useEffect(() => {
		if (transport === undefined) {
			return undefined;
		}
		const live = new BridgeClient(
			transport,
			timeoutMs === undefined ? {} : { timeoutMs },
		);
		setOwned(live);
		return () => {
			live.close();
			setOwned((current) => (current === live ? null : current));
		};
	}, [transport, timeoutMs]);
	const value = useMemo((): Shared | null => {
		if (qgis !== undefined) {
			return { client: qgis.client, qgis };
		}
		const live = client ?? owned;
		return live === null ? null : { client: live, qgis: null };
	}, [qgis, client, owned]);
	return createElement(
		ClientContext.Provider,
		{ value },
		value === null ? null : children,
	);
}

function useShared(hook: string): Shared {
	const shared = useContext(ClientContext);
	if (shared === null) {
		throw new QgisSdkBridgeReactError(
			`${hook} needs a BridgeProvider above it`,
		);
	}
	return shared;
}

/** The client of the nearest {@link BridgeProvider}. */
export function useBridgeClient(): BridgeClient {
	return useShared("useBridgeClient").client;
}

/**
 * The `QgisSdk` of the nearest {@link BridgeProvider}.
 *
 * The type parameters name the generated `Operations` and `Streams`; they are
 * the caller's claim, the same way the provider's `qgis` prop was the page's.
 */
export function useQgisSdk<O = OperationMap, S = StreamMap>(): QgisSdk<O, S> {
	const shared = useShared("useQgisSdk");
	if (shared.qgis === null) {
		throw new QgisSdkBridgeReactError(
			"useQgisSdk needs a BridgeProvider given a qgis instance",
		);
	}
	return shared.qgis as unknown as QgisSdk<O, S>;
}

/**
 * Build a generated operation map once per client: `useOperations(createOperations)`.
 */
export function useOperations<T>(create: (client: BridgeClient) => T): T {
	const client = useBridgeClient();
	return useMemo(() => create(client), [create, client]);
}

/** Controls beyond running: abort what is in flight, or forget the outcome. */
export interface OperationControls {
	/** Abort the in-flight call locally; the host may still run it. */
	abort(): void;
	/** Back to `idle`, aborting anything in flight. */
	reset(): void;
}

/** Read any store from a component; the snapshot is the render's value. */
export function useStore<T>(store: Store<T>): T {
	return useSyncExternalStore(
		store.subscribe,
		store.getSnapshot,
		store.getSnapshot,
	);
}

/**
 * Run a generated operation from a component.
 *
 * `run` resolves with the value, or with `undefined` when the call failed, was
 * aborted or was superseded by a later run - the state carries the error, so
 * the promise never rejects into an event handler. Only the latest run can
 * change the state; unmounting aborts whatever is in flight.
 */
export function useOperation<I, R>(
	operation: Operation<I, R>,
): readonly [
	OperationState<R>,
	(input: I) => Promise<R | undefined>,
	OperationControls,
] {
	const store = useMemo(() => new OperationStore(operation), [operation]);
	useEffect(() => () => store.abort(), [store]);
	const state = useStore(store);
	const controls = useMemo(
		() => ({ abort: store.abort, reset: store.reset }),
		[store],
	);
	return [state, store.run, controls];
}

/**
 * Hold a generated stream open while a component is mounted.
 *
 * The subscription follows `open` and the *content* of `input`: a new object
 * with the same fields does not reopen it, a different one closes the old
 * stream and opens a new one, and `null` closes it. Handlers are read fresh
 * on every frame, so a new closure does not reopen anything either. Unmount
 * closes the stream, even if the host has not yet acknowledged it.
 */
export function useStream<I, E>(
	open: Stream<I, E>,
	input: I | null,
	handlers: StreamHandlersLike<E> = {},
): StreamState<E> {
	const store = useMemo(() => new StreamStore(open), [open]);
	store.setHandlers(handlers);
	// The store keys the input by content, so an effect per render is cheap
	// and a new object with the same fields reopens nothing.
	useEffect(() => {
		store.setInput(input);
	});
	useEffect(() => () => store.close(), [store]);
	return useStore(store);
}

/**
 * The form of one declared action: `qgis.<id>` with its fields, values,
 * issues and submission. The store is built once per `qgis` and `id` - the
 * options are read on the first render only, like `useState`'s initial value
 * - and unmounting aborts a submission in flight.
 */
export function useForm<O, K extends keyof O & string>(
	qgis: QgisSdkCore<O, unknown>,
	id: K,
	options?: FormOptions,
): readonly [
	FormState<ResultOf<O, K>>,
	FormStore<RequestOf<O, K> & object, ResultOf<O, K>>,
] {
	const [first] = useState(() => options ?? {});
	const store = useMemo(
		() =>
			new FormStore<RequestOf<O, K> & object, ResultOf<O, K>>(
				qgis as QgisSdkCore<unknown, unknown>,
				id,
				first,
			),
		[qgis, id, first],
	);
	// Abort, not dispose: StrictMode's simulated unmount keeps the store.
	useEffect(() => () => store.abort(), [store]);
	return [useStore(store), store];
}

/**
 * Read a host query store: `useHostQuery(layersQuery(qgis))` for a layer
 * picker. `refresh` runs once on mount when `auto` is not `false`.
 */
export function useHostQuery<T>(
	store: HostQueryStore<T>,
	options: { readonly auto?: boolean } = {},
): readonly [HostQueryState<T>, HostQueryStore<T>] {
	const auto = options.auto !== false;
	useEffect(() => {
		if (auto) {
			void store.refresh();
		}
		return () => store.abort();
	}, [store, auto]);
	return [useStore(store), store];
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
