/** {@link StreamStore}: one generated stream held open while its input is non-null. */

import { isPlainRecord } from "../internal";
import { asError, BaseStore } from "./base";

// ---------------------------------------------------------------------------
// StreamStore
// ---------------------------------------------------------------------------

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

/**
 * Return a key that is equal for two inputs with the same content, whatever
 * the order their fields were written in.
 */
export function stableKey(value: unknown): string {
	return JSON.stringify(value, (_key, item: unknown) =>
		isPlainRecord(item)
			? Object.fromEntries(
					Object.entries(item).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
				)
			: item,
	);
}

/**
 * Hold one generated stream open while its input is non-null.
 *
 * `setInput` follows the *content* of the input: a new object with the same
 * fields changes nothing, a different one closes the old stream and opens a
 * new one, `null` closes it. Handlers are read fresh on every frame, so
 * `setHandlers` with a new closure reopens nothing. `close` is safe before the
 * host has acknowledged the stream: the handle is closed the moment it
 * arrives.
 */
export class StreamStore<I, E> extends BaseStore<StreamState<E>> {
	private key: string | null = null;
	private cancel: (() => void) | null = null;

	public constructor(
		private readonly open: Stream<I, E>,
		private handlers: StreamHandlersLike<E> = {},
	) {
		super(IDLE_STREAM);
	}

	/** Replace the handlers the next frames reach; nothing reopens. */
	public setHandlers(handlers: StreamHandlersLike<E>): void {
		this.handlers = handlers;
	}

	public readonly setInput = (input: I | null): void => {
		const key = input === null ? null : stableKey(input);
		if (key === this.key) {
			return;
		}
		this.cancel?.();
		this.cancel = null;
		this.key = key;
		if (input === null || key === null) {
			this.publish(IDLE_STREAM);
			return;
		}
		this.cancel = this.start(input);
	};

	public readonly close = (): void => {
		this.setInput(null);
	};

	private start(input: I): () => void {
		let cancelled = false;
		let handle: StreamHandleLike | null = null;
		const update = (change: (previous: StreamState<E>) => StreamState<E>) => {
			if (!cancelled) {
				this.publish(change(this.getSnapshot()));
			}
		};
		this.publish({
			status: "opening",
			lastEvent: null,
			terminal: null,
			error: null,
		});
		this.open(input, {
			onEvent: (event) => {
				if (cancelled) {
					return;
				}
				this.handlers.onEvent?.(event);
				update((previous) => ({ ...previous, lastEvent: event }));
			},
			onTerminal: (terminal) => {
				if (cancelled) {
					return;
				}
				this.handlers.onTerminal?.(terminal);
				update((previous) => ({ ...previous, status: "ended", terminal }));
			},
		}).then(
			(opened) => {
				if (cancelled) {
					opened.close();
					return;
				}
				handle = opened;
				update((previous) =>
					previous.status === "ended"
						? previous
						: { ...previous, status: "open" },
				);
			},
			(error: unknown) => {
				update(() => ({
					status: "failed",
					lastEvent: null,
					terminal: null,
					error: asError(error),
				}));
			},
		);
		return () => {
			cancelled = true;
			handle?.close();
		};
	}
}
