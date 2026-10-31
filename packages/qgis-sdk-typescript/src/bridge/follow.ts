/**
 * Following a stream across a gap: reopen it, and say that you did.
 *
 * The host bounds what is in flight and terminates a subscription with `gap`
 * when a pushed producer outruns the queue (decision-59). A page that treats
 * `gap` like `complete` silently shows stale data; a page that reopens it
 * without saying so hides that frames were lost. This module is the third
 * option: reopen, report the resume with the terminal that caused it, and stop
 * after a caller-set number of attempts so a broken stream cannot spin.
 *
 * Nothing here resumes mid-stream - the protocol has no cursor for that - so a
 * reopened subscription starts at seq 0 again, and the caller decides whether
 * to replace or merge what it already rendered.
 */

import type {
	BridgeClient,
	BridgeSubscription,
	SubscriptionHandlers,
} from "./client";
import type { BridgeStreamTerminal } from "./protocol";

/** Options for {@link followSubscription}. */
export interface FollowOptions {
	/** How many times to reopen after a terminal the caller says is retryable. */
	readonly maxResubscribes?: number;
	/**
	 * Which terminals are worth reopening. Defaults to `gap` alone: `complete`,
	 * `cancelled` and `disposed` are answers, and retrying them would turn a
	 * finished stream into a loop. An `error` is the host saying no, and a page
	 * that retries it hammers a failure it cannot fix.
	 */
	readonly retryOn?: (terminal: BridgeStreamTerminal) => boolean;
	/** Called after a reopen succeeded, with what the previous attempt ended on. */
	readonly onResume?: (info: {
		readonly attempt: number;
		readonly dropped: number;
		readonly terminal: BridgeStreamTerminal;
	}) => void;
}

/** A stream being followed, as the caller holds it. */
export interface FollowedStream {
	/** `false` once {@link FollowedStream.close} ran or the follow gave up. */
	readonly closed: boolean;
	/** How many subscriptions were opened, the first one included. */
	readonly attempts: number;
	/** The subscription currently open, if any. */
	readonly subscriptionId: string | null;
	/**
	 * Resolves once the first subscription is open, so a caller can emit into a
	 * scripted host only after the client has registered the id. Rejects when the
	 * host refused the first attempt.
	 */
	readonly ready: Promise<void>;
	close(): void;
}

const DEFAULT_MAX_RESUBSCRIBES = 3;

/**
 * Open `operation` and reopen it when it ends in a way worth retrying.
 *
 * The handlers see every event of every attempt; `onTerminal` sees the terminal
 * of each attempt, including the ones that lead to a reopen, so a caller that
 * finished rendering can tell a recovered stream from a broken one. A terminal
 * caused by {@link FollowedStream.close} is reported as `disposed`.
 */
export function followSubscription(
	client: BridgeClient,
	operation: string,
	payload: Readonly<Record<string, unknown>> = {},
	handlers: SubscriptionHandlers = {},
	options: FollowOptions = {},
): FollowedStream {
	const maxResubscribes = options.maxResubscribes ?? DEFAULT_MAX_RESUBSCRIBES;
	const retryOn = options.retryOn ?? ((terminal) => terminal.kind === "gap");
	let subscription: BridgeSubscription | null = null;
	let closed = false;
	let attempts = 0;
	let resubscribes = 0;
	// Assigned by the executor below, which runs before this call returns.
	let settleReady: (() => void) | undefined;
	let refuseReady: ((error: unknown) => void) | undefined;
	const ready = new Promise<void>((resolve, reject) => {
		settleReady = resolve;
		refuseReady = reject;
	});
	// A caller that never awaits `ready` still sees its handlers fire; the
	// rejection is not left unobserved on top of that.
	ready.catch(() => undefined);

	const handle: FollowedStream = {
		get closed(): boolean {
			return closed;
		},
		get attempts(): number {
			return attempts;
		},
		get subscriptionId(): string | null {
			return subscription?.id ?? null;
		},
		ready,
		close: (): void => {
			if (closed) {
				return;
			}
			closed = true;
			const open = subscription;
			subscription = null;
			open?.close();
		},
	};

	// Every caller has already checked `closed` - the first open happens while it
	// is false and a reopen only follows a terminal that did not close us - so
	// opening again here would be a second guard on the same fact.
	const open = (): void => {
		attempts += 1;
		client
			.subscribe(operation, payload, {
				onEvent: (event) => {
					if (!closed) {
						handlers.onEvent?.(event);
					}
				},
				onTerminal: (terminal) => {
					const ending = closed
						? ({ kind: "disposed" } as BridgeStreamTerminal)
						: terminal;
					handlers.onTerminal?.(ending);
					if (closed) {
						return;
					}
					if (!retryOn(terminal) || resubscribes >= maxResubscribes) {
						closed = true;
						subscription = null;
						return;
					}
					resubscribes += 1;
					subscription = null;
					options.onResume?.({
						attempt: attempts + 1,
						dropped: terminal.dropped ?? 0,
						terminal,
					});
					open();
				},
			})
			.then((opened) => {
				if (closed) {
					opened.close();
					return;
				}
				subscription = opened;
				settleReady?.();
			})
			.catch((error: unknown) => {
				if (closed) {
					return;
				}
				closed = true;
				refuseReady?.(error);
				handlers.onTerminal?.({
					kind: "error",
					message: error instanceof Error ? error.message : "the host refused",
				});
			});
	};

	open();
	return handle;
}
