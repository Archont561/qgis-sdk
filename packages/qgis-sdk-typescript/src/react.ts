/**
 * Thin React bindings over the bridge client (TASK-18, decision-18).
 *
 * This entry point is optional and is the only one that imports React. It adds
 * no second client: a component reaches the same `QgisSdk` or `BridgeClient` a
 * vanilla page would build, through a provider that is handed a `QgisSdk`
 * (and leaves it alone), is handed a client (same), or owns a client built on
 * a transport (and closes it on unmount). The hooks take the methods a
 * `QgisSdk` already has - `qgis["sites.summary"]`, `qgis["sites.watch"]` - so
 * the typed contract is the generated one, not a React copy of it.
 *
 * What the hooks add is lifetime: a call aborted when its component unmounts,
 * a stale reply ignored, a stream closed on unmount or when its input changes,
 * and a simulated StrictMode remount that leaves exactly one of each.
 */

import {
	createContext,
	createElement,
	type ReactElement,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	BridgeClient,
	type BridgeClientOptions,
	QgisSdkBridgeAbortedError,
	type WireTransport,
} from "./bridge";
import { QgisSdkError } from "./errors";
import { isPlainRecord } from "./internal";
import type { QgisSdk, QgisSdkCore } from "./qgis-sdk";
import type { OperationMap, StreamMap } from "./schema";

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

/** Where one invocation stands. */
export type OperationState<R> =
	| { readonly status: "idle" }
	| { readonly status: "pending" }
	| { readonly status: "ok"; readonly value: R }
	| { readonly status: "error"; readonly error: Error };

/** Controls beyond running: abort what is in flight, or forget the outcome. */
export interface OperationControls {
	/** Abort the in-flight call locally; the host may still run it. */
	abort(): void;
	/** Back to `idle`, aborting anything in flight. */
	reset(): void;
}

/** An operation member of a generated map: input, optional signal, promise. */
export type Operation<I, R> = (
	input: I,
	options?: { readonly signal?: AbortSignal },
) => Promise<R>;

const IDLE: OperationState<never> = Object.freeze({ status: "idle" });
const PENDING: OperationState<never> = Object.freeze({ status: "pending" });

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
	const [state, setState] = useState<OperationState<R>>(IDLE);
	const generation = useRef(0);
	const controller = useRef<AbortController | null>(null);
	const mounted = useRef(true);

	const abort = useCallback((): void => {
		generation.current += 1;
		controller.current?.abort();
		controller.current = null;
	}, []);

	useEffect(() => {
		mounted.current = true;
		return () => {
			mounted.current = false;
			abort();
		};
	}, [abort]);

	const run = useCallback(
		async (input: I): Promise<R | undefined> => {
			abort();
			const mine = generation.current;
			const signal = new AbortController();
			controller.current = signal;
			setState(PENDING);
			try {
				const value = await operation(input, { signal: signal.signal });
				if (generation.current !== mine || !mounted.current) {
					return undefined;
				}
				setState({ status: "ok", value });
				return value;
			} catch (error) {
				if (generation.current !== mine || !mounted.current) {
					return undefined;
				}
				if (error instanceof QgisSdkBridgeAbortedError) {
					return undefined;
				}
				setState({
					status: "error",
					error: error instanceof Error ? error : new Error(String(error)),
				});
				return undefined;
			} finally {
				if (controller.current === signal) {
					controller.current = null;
				}
			}
		},
		[operation, abort],
	);

	const reset = useCallback((): void => {
		abort();
		setState(IDLE);
	}, [abort]);

	const controls = useMemo(() => ({ abort, reset }), [abort, reset]);
	return [state, run, controls];
}

/** How a stream ended, as the generated module reports it. */
export interface StreamTerminalLike {
	readonly kind: string;
	readonly message?: string;
	readonly dropped?: number;
}

/** The handle a generated stream member resolves with. */
export interface StreamHandleLike {
	readonly id: string;
	readonly closed: boolean;
	close(): void;
}

/** Handlers for a stream, as a generated module types them. */
export interface StreamHandlersLike<E> {
	readonly onEvent?: (event: E) => void;
	readonly onTerminal?: (terminal: StreamTerminalLike) => void;
}

/** A stream member of a generated map. */
export type Stream<I, E> = (
	input: I,
	handlers: StreamHandlersLike<E>,
	options?: { readonly signal?: AbortSignal },
) => Promise<StreamHandleLike>;

/** Where one subscription stands. */
export interface StreamState<E> {
	/** `idle` with a null input, `failed` when the host refused to open it. */
	readonly status: "idle" | "opening" | "open" | "ended" | "failed";
	readonly lastEvent: E | null;
	readonly terminal: StreamTerminalLike | null;
	readonly error: Error | null;
}

const IDLE_STREAM: StreamState<never> = Object.freeze({
	status: "idle",
	lastEvent: null,
	terminal: null,
	error: null,
});

function stableKey(value: unknown): string {
	return JSON.stringify(value, (_key, item: unknown) =>
		isPlainRecord(item)
			? Object.fromEntries(
					Object.entries(item).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
				)
			: item,
	);
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
	const [state, setState] = useState<StreamState<E>>(IDLE_STREAM);
	const latest = useRef(handlers);
	latest.current = handlers;
	const key = input === null ? null : stableKey(input);
	// `input` is deliberately read through `key`: two objects with the same
	// fields are the same subscription.
	const inputRef = useRef(input);
	inputRef.current = input;

	useEffect(() => {
		if (key === null) {
			setState(IDLE_STREAM);
			return undefined;
		}
		const current = inputRef.current as I;
		let cancelled = false;
		let handle: StreamHandleLike | null = null;
		setState({
			status: "opening",
			lastEvent: null,
			terminal: null,
			error: null,
		});
		open(current, {
			onEvent: (event) => {
				if (cancelled) {
					return;
				}
				latest.current.onEvent?.(event);
				setState((previous) => ({ ...previous, lastEvent: event }));
			},
			onTerminal: (terminal) => {
				if (cancelled) {
					return;
				}
				latest.current.onTerminal?.(terminal);
				setState((previous) => ({ ...previous, status: "ended", terminal }));
			},
		}).then(
			(opened) => {
				if (cancelled) {
					opened.close();
					return;
				}
				handle = opened;
				setState((previous) =>
					previous.status === "ended"
						? previous
						: { ...previous, status: "open" },
				);
			},
			(error: unknown) => {
				if (cancelled) {
					return;
				}
				setState({
					status: "failed",
					lastEvent: null,
					terminal: null,
					error: error instanceof Error ? error : new Error(String(error)),
				});
			},
		);
		return () => {
			cancelled = true;
			handle?.close();
		};
	}, [open, key]);

	return state;
}
