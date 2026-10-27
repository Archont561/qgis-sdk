/** {@link BridgeClient}: invocations correlated with replies over an injected transport. */

import { isPlainRecord } from "../internal";
import {
	QgisSdkBridgeAbortedError,
	QgisSdkBridgeClosedError,
	QgisSdkBridgeProtocolError,
	QgisSdkBridgeRemoteError,
	QgisSdkBridgeTimeoutError,
} from "./errors";
import { isNonEmptyString, parseInvokeReply, parseStreamFrame } from "./frames";
import {
	BRIDGE_PROTOCOL_VERSION,
	type BridgeClientOptions,
	type BridgeStreamEvent,
	type BridgeStreamFrame,
	type BridgeStreamTerminal,
	type InvokeOptions,
	type InvokeReply,
	type WireTransport,
} from "./protocol";

/** Callbacks a subscription reports through. */
export interface SubscriptionHandlers {
	readonly onEvent?: (event: BridgeStreamEvent) => void;
	readonly onTerminal?: (terminal: BridgeStreamTerminal) => void;
}

/** A live subscription, as the caller holds it. */
export interface BridgeSubscription {
	readonly id: string;
	readonly closed: boolean;
	close(): void;
}

interface OpenSubscription {
	readonly id: string;
	readonly handlers: SubscriptionHandlers;
	expectedSeq: number;
	closed: boolean;
}

interface PendingCall {
	readonly resolve: (value: unknown) => void;
	readonly reject: (error: Error) => void;
	readonly timer: ReturnType<typeof setTimeout> | null;
	readonly detach: (() => void) | null;
}

/**
 * Correlate invocations with replies over an injected transport.
 *
 * The client never retries: a timeout, an abort and a closed client are three
 * different answers, and each is reported as itself.
 */
export class BridgeClient {
	private readonly transport: WireTransport;
	private readonly timeoutMs: number;
	private readonly pending: Map<string, PendingCall> = new Map();
	private readonly subscriptions: Map<string, OpenSubscription> = new Map();
	private readonly disposals: Set<string> = new Set();
	private readonly unsubscribe: () => void;
	private counter: number = 0;
	private closed: boolean = false;
	private unmatched: number = 0;
	private breaks: number = 0;
	private lastProtocolError: Error | null = null;

	public constructor(
		transport: WireTransport,
		options: BridgeClientOptions = {},
	) {
		this.transport = transport;
		this.timeoutMs = options.timeoutMs ?? 30_000;
		this.unsubscribe = transport.subscribe((message) => {
			this.handle(message);
		});
	}

	/** Whether {@link close} has run; a closed client answers nothing. */
	public get isClosed(): boolean {
		return this.closed;
	}

	/** Replies that named no pending call: a late duplicate, or a stray message. */
	public get unmatchedReplies(): number {
		return this.unmatched;
	}

	/** Number of calls still waiting for a reply. */
	public get pendingCalls(): number {
		return this.pending.size;
	}

	/**
	 * Invoke one operation and settle with its value or with a typed failure.
	 */
	public invoke(
		operation: string,
		payload: Readonly<Record<string, unknown>> = {},
		options: InvokeOptions = {},
	): Promise<unknown> {
		if (!isNonEmptyString(operation)) {
			return Promise.reject(
				new QgisSdkBridgeProtocolError("operation must be a nonempty string"),
			);
		}
		return this.send({ kind: "invoke", operation, payload }, options);
	}

	/**
	 * Open a subscription and resolve once the host has acknowledged it.
	 *
	 * Frames are matched to the subscription by id and by sequence; a frame that
	 * does not continue the sequence ends the subscription instead of being
	 * delivered out of order.
	 */
	public subscribe(
		operation: string,
		payload: Readonly<Record<string, unknown>> = {},
		handlers: SubscriptionHandlers = {},
		options: InvokeOptions = {},
	): Promise<BridgeSubscription> {
		if (!isNonEmptyString(operation)) {
			return Promise.reject(
				new QgisSdkBridgeProtocolError("operation must be a nonempty string"),
			);
		}
		return this.send({ kind: "subscribe", operation, payload }, options).then(
			(value) => {
				const id = isPlainRecord(value) ? value.subscription_id : undefined;
				if (!isNonEmptyString(id)) {
					throw new QgisSdkBridgeProtocolError(
						"A subscription acknowledgement must carry a subscription_id",
					);
				}
				const open: OpenSubscription = {
					id,
					handlers,
					expectedSeq: 0,
					closed: false,
				};
				this.subscriptions.set(id, open);
				const handle: BridgeSubscription = {
					id,
					get closed(): boolean {
						return open.closed;
					},
					close: (): void => {
						this.endSubscription(id, { kind: "disposed" }, true);
					},
				};
				return handle;
			},
		);
	}

	/**
	 * Ask the host for the handshake: the contract this view may use.
	 *
	 * The host bound the view before its first message, so this is a call, not
	 * a binding. The value is what `Dispatcher.handshake` builds - protocol,
	 * generation, the plugin description, the host schema version and the
	 * operations this view is authorized for.
	 */
	public handshake(options: InvokeOptions = {}): Promise<unknown> {
		return this.send({ kind: "handshake" }, options);
	}

	/** Subscriptions still open; a leak check for callers and tests. */
	public get activeSubscriptions(): readonly string[] {
		return [...this.subscriptions.keys()];
	}

	/** Frames that did not continue their subscription's sequence. */
	public get sequenceBreaks(): number {
		return this.breaks;
	}

	private send(
		body: Readonly<Record<string, unknown>>,
		options: InvokeOptions,
	): Promise<unknown> {
		if (this.closed) {
			return Promise.reject(new QgisSdkBridgeClosedError());
		}
		this.counter += 1;
		const callId = `c${this.counter}`;

		const promise = new Promise<unknown>((resolve, reject) => {
			if (options.signal?.aborted === true) {
				reject(new QgisSdkBridgeAbortedError(callId));
				return;
			}
			const onAbort = (): void => {
				const pending = this.pending.get(callId);
				if (pending === undefined) {
					return;
				}
				this.settle(callId);
				pending.reject(new QgisSdkBridgeAbortedError(callId));
			};
			options.signal?.addEventListener("abort", onAbort, { once: true });

			const timer =
				this.timeoutMs > 0
					? setTimeout(() => {
							const pending = this.pending.get(callId);
							if (pending === undefined) {
								return;
							}
							this.settle(callId);
							pending.reject(
								new QgisSdkBridgeTimeoutError(callId, this.timeoutMs),
							);
						}, this.timeoutMs)
					: null;

			const detach =
				options.signal === undefined
					? null
					: (): void => {
							options.signal?.removeEventListener("abort", onAbort);
						};

			this.pending.set(callId, { resolve, reject, timer, detach });
			this.transport.send({
				protocol: BRIDGE_PROTOCOL_VERSION,
				call_id: callId,
				...body,
			});
		});

		return promise;
	}

	/**
	 * Refuse further calls, reject what is still pending, and stop listening.
	 */
	public close(): void {
		if (this.closed) {
			return;
		}
		this.closed = true;
		this.unsubscribe();
		for (const id of [...this.subscriptions.keys()]) {
			this.endSubscription(id, { kind: "disposed" }, false);
		}
		for (const callId of [...this.pending.keys()]) {
			const pending = this.pending.get(callId);
			if (pending === undefined) {
				continue;
			}
			this.settle(callId);
			pending.reject(new QgisSdkBridgeClosedError());
		}
	}

	private settle(callId: string): PendingCall | undefined {
		const pending = this.pending.get(callId);
		if (pending === undefined) {
			return undefined;
		}
		this.pending.delete(callId);
		if (pending.timer !== null) {
			clearTimeout(pending.timer);
		}
		pending.detach?.();
		return pending;
	}

	private handle(message: unknown): void {
		if (isPlainRecord(message) && Object.hasOwn(message, "subscription_id")) {
			this.handleFrame(message);
			return;
		}
		let reply: InvokeReply;
		try {
			reply = parseInvokeReply(message);
		} catch (error) {
			// A malformed message cannot be attributed to a call, so it cannot
			// settle one: the call keeps waiting and eventually times out, which
			// is the honest answer about an outcome the client could not read.
			this.unmatched += 1;
			if (error instanceof Error) {
				this.lastProtocolError = error;
			}
			return;
		}
		if (this.disposals.delete(reply.call_id)) {
			return;
		}
		const pending = this.settle(reply.call_id);
		if (pending === undefined) {
			this.unmatched += 1;
			return;
		}
		if (reply.ok) {
			pending.resolve(reply.value);
			return;
		}
		pending.reject(new QgisSdkBridgeRemoteError(reply.call_id, reply.error));
	}

	private handleFrame(raw: unknown): void {
		let frame: BridgeStreamFrame;
		try {
			frame = parseStreamFrame(raw);
		} catch (error) {
			// A frame that cannot be parsed cannot be attributed either, so it is
			// counted rather than delivered to whatever subscription looks closest.
			this.unmatched += 1;
			if (error instanceof Error) {
				this.lastProtocolError = error;
			}
			return;
		}
		const open = this.subscriptions.get(frame.subscription_id);
		if (open === undefined) {
			this.unmatched += 1;
			return;
		}
		if (frame.seq !== open.expectedSeq) {
			this.breaks += 1;
			const expected = open.expectedSeq;
			this.endSubscription(
				frame.subscription_id,
				{
					kind: "gap",
					message: `Expected frame ${expected} but received ${frame.seq}`,
					dropped: Math.max(0, frame.seq - expected),
				},
				true,
			);
			return;
		}
		open.expectedSeq += 1;
		if ("terminal" in frame) {
			this.endSubscription(frame.subscription_id, frame.terminal, false);
			return;
		}
		open.handlers.onEvent?.(frame.event);
	}

	private endSubscription(
		id: string,
		terminal: BridgeStreamTerminal,
		notifyHost: boolean,
	): void {
		const open = this.subscriptions.get(id);
		if (open === undefined || open.closed) {
			return;
		}
		open.closed = true;
		this.subscriptions.delete(id);
		if (notifyHost) {
			this.disposeSubscription(id);
		}
		open.handlers.onTerminal?.(terminal);
	}

	private disposeSubscription(id: string): void {
		if (this.closed) {
			return;
		}
		this.counter += 1;
		const callId = `c${this.counter}`;
		this.disposals.add(callId);
		this.transport.send({
			protocol: BRIDGE_PROTOCOL_VERSION,
			call_id: callId,
			kind: "unsubscribe",
			subscription_id: id,
		});
	}

	/** The last malformed message this client refused, if any. */
	public get protocolError(): Error | null {
		return this.lastProtocolError;
	}
}
