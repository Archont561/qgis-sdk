/**
 * The versioned transport contract a web view speaks.
 *
 * This module is the client half of `qgis_sdk.bridge`: it parses the replies the
 * host produces, correlates them by call id, and refuses anything that does not
 * match the protocol instead of guessing. It is deliberately usable without a
 * QWebChannel - the transport is injected - so failures can be scripted in a
 * test rather than reproduced inside a running QGIS.
 *
 * Two properties matter more than the API surface:
 *
 * - A malformed reply is refused, never coerced. A frontend that accepts
 *   `{ok: "yes"}` or an error without a code ends up switching on text.
 * - A local timeout says nothing about the host. The call may have run, so it is
 *   reported as an unknown outcome and is never retried automatically.
 */

import type { StreamEventKind } from "./declarations";
import { QgisSdkError } from "./errors";
import { isPlainRecord, STREAM_EVENT_KINDS } from "./internal";

export type { StreamEventKind };

export const BRIDGE_PROTOCOL_VERSION: 1 = 1;
export const MAX_CALL_ID_LENGTH: number = 128;

/** A failure reply, as the host serialized it. */
export interface BridgeFailure {
	readonly code: string;
	readonly message: string;
}

/** A reply to one invocation: exactly one of `value` or `error` is present. */
export type InvokeReply =
	| {
			readonly protocol: 1;
			readonly call_id: string;
			readonly ok: true;
			readonly value: unknown;
	  }
	| {
			readonly protocol: 1;
			readonly call_id: string;
			readonly ok: false;
			readonly error: BridgeFailure;
	  };

/** Why a subscription stopped. */
export type StreamTerminalKind =
	| "complete"
	| "error"
	| "cancelled"
	| "gap"
	| "disposed";

/** One event on a subscription. */
export interface BridgeStreamEvent {
	readonly kind: StreamEventKind;
	readonly payload: unknown;
}

/** The end of a subscription, as the host described it. */
export interface BridgeStreamTerminal {
	readonly kind: StreamTerminalKind;
	readonly message?: string;
	readonly dropped?: number;
}

/** A frame carrying one event. */
export interface BridgeEventFrame {
	readonly protocol: 1;
	readonly subscription_id: string;
	readonly seq: number;
	readonly event: BridgeStreamEvent;
}

/** The frame that ends a subscription. */
export interface BridgeTerminalFrame {
	readonly protocol: 1;
	readonly subscription_id: string;
	readonly seq: number;
	readonly terminal: BridgeStreamTerminal;
}

/** Anything the host may send for a subscription. */
export type BridgeStreamFrame = BridgeEventFrame | BridgeTerminalFrame;

/** The transport a client speaks through; a QWebChannel adapter or a script. */
export interface WireTransport {
	send(message: unknown): void;
	subscribe(listener: (message: unknown) => void): () => void;
}

/** Options for {@link BridgeClient}. */
export interface BridgeClientOptions {
	readonly timeoutMs?: number;
}

/** Options for one invocation. */
export interface InvokeOptions {
	readonly signal?: AbortSignal;
}

/**
 * An envelope or reply does not match the versioned bridge protocol.
 */
export class QgisSdkBridgeProtocolError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "invalid_bridge_message");
	}
}

/**
 * The host did not answer in time. The call may still have run, so this is an
 * unknown outcome: retrying automatically is forbidden, deciding is the caller's.
 */
export class QgisSdkBridgeTimeoutError extends QgisSdkError {
	public readonly callId: string;

	public constructor(callId: string, timeoutMs: number) {
		super(
			`Call ${JSON.stringify(callId)} got no reply within ${timeoutMs}ms; the host may still have run it`,
			"timeout",
		);
		this.callId = callId;
	}
}

/**
 * The caller aborted locally. Distinct from the host cancelling the operation,
 * which arrives as a failure reply carrying the `cancelled` code.
 */
export class QgisSdkBridgeAbortedError extends QgisSdkError {
	public readonly callId: string;

	public constructor(callId: string) {
		super(`Call ${JSON.stringify(callId)} was aborted locally`, "aborted");
		this.callId = callId;
	}
}

/**
 * The client was closed, so pending calls can no longer be answered.
 */
export class QgisSdkBridgeClosedError extends QgisSdkError {
	public constructor() {
		super("This bridge client is closed", "closed");
	}
}

/**
 * A subscription's frames were not the sequence the host promised.
 *
 * The client does not try to reassemble: a missed frame is a fact about the
 * subscription, not something to paper over.
 */
export class QgisSdkBridgeSequenceError extends QgisSdkError {
	public readonly subscriptionId: string;
	public readonly expected: number;
	public readonly received: number;

	public constructor(
		subscriptionId: string,
		expected: number,
		received: number,
	) {
		super(
			`Subscription ${JSON.stringify(subscriptionId)} expected frame ${expected} but received ${received}`,
			"stream_gap",
		);
		this.subscriptionId = subscriptionId;
		this.expected = expected;
		this.received = received;
	}
}

/**
 * The subscription ended with a terminal frame the caller may want to inspect.
 */
export class QgisSdkBridgeStreamEndedError extends QgisSdkError {
	public readonly subscriptionId: string;
	public readonly terminal: BridgeStreamTerminal;

	public constructor(subscriptionId: string, terminal: BridgeStreamTerminal) {
		super(
			terminal.message ??
				`Subscription ${JSON.stringify(subscriptionId)} ended: ${terminal.kind}`,
			terminal.kind,
		);
		this.subscriptionId = subscriptionId;
		this.terminal = terminal;
	}
}

/**
 * The host refused or failed the operation; `failure.code` is the contract.
 */
export class QgisSdkBridgeRemoteError extends QgisSdkError {
	public readonly failure: BridgeFailure;
	public readonly callId: string;

	public constructor(callId: string, failure: BridgeFailure) {
		super(failure.message, failure.code);
		this.callId = callId;
		this.failure = failure;
	}
}

function isNonEmptyString(value: unknown): value is string {
	return typeof value === "string" && value.trim().length > 0;
}

/**
 * Parse one reply, refusing anything the host could not legitimately have sent.
 */
export function parseInvokeReply(raw: unknown): InvokeReply {
	if (!isPlainRecord(raw)) {
		throw new QgisSdkBridgeProtocolError("A reply must be an object");
	}
	if (raw.protocol !== BRIDGE_PROTOCOL_VERSION) {
		throw new QgisSdkBridgeProtocolError(
			`Unsupported bridge protocol: ${String(raw.protocol)}; this client speaks ${BRIDGE_PROTOCOL_VERSION}`,
		);
	}
	if (
		!isNonEmptyString(raw.call_id) ||
		raw.call_id.length > MAX_CALL_ID_LENGTH
	) {
		throw new QgisSdkBridgeProtocolError(
			`call_id must be a nonempty string of at most ${MAX_CALL_ID_LENGTH} characters`,
		);
	}
	const callId = raw.call_id;
	if (typeof raw.ok !== "boolean") {
		throw new QgisSdkBridgeProtocolError(`${callId}: ok must be a boolean`);
	}
	if (raw.ok) {
		if (!Object.hasOwn(raw, "value")) {
			throw new QgisSdkBridgeProtocolError(
				`${callId}: a success reply must carry a value`,
			);
		}
		return Object.freeze({
			protocol: BRIDGE_PROTOCOL_VERSION,
			call_id: callId,
			ok: true as const,
			value: raw.value,
		});
	}
	if (!isPlainRecord(raw.error)) {
		throw new QgisSdkBridgeProtocolError(
			`${callId}: a failure reply must carry an error object`,
		);
	}
	if (!isNonEmptyString(raw.error.code)) {
		throw new QgisSdkBridgeProtocolError(
			`${callId}: error.code must be a string`,
		);
	}
	if (typeof raw.error.message !== "string") {
		throw new QgisSdkBridgeProtocolError(
			`${callId}: error.message must be a string`,
		);
	}
	return Object.freeze({
		protocol: BRIDGE_PROTOCOL_VERSION,
		call_id: callId,
		ok: false as const,
		error: Object.freeze({
			code: raw.error.code,
			message: raw.error.message,
		}),
	});
}

function isIndex(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

const TERMINAL_KINDS: readonly StreamTerminalKind[] = [
	"cancelled",
	"complete",
	"disposed",
	"error",
	"gap",
];

/**
 * Parse one stream frame, refusing anything the host could not legitimately
 * have sent.
 *
 * Exactly one of `event` and `terminal` has to be present: a frame that carries
 * both leaves the client guessing which one wins, and a client that guesses is
 * a client that will eventually deliver an event after the end of a stream.
 */
export function parseStreamFrame(raw: unknown): BridgeStreamFrame {
	if (!isPlainRecord(raw)) {
		throw new QgisSdkBridgeProtocolError("A stream frame must be an object");
	}
	if (raw.protocol !== BRIDGE_PROTOCOL_VERSION) {
		throw new QgisSdkBridgeProtocolError(
			`Unsupported bridge protocol: ${String(raw.protocol)}; this client speaks ${BRIDGE_PROTOCOL_VERSION}`,
		);
	}
	if (!isNonEmptyString(raw.subscription_id)) {
		throw new QgisSdkBridgeProtocolError(
			"A stream frame must name its subscription",
		);
	}
	if (!isIndex(raw.seq)) {
		throw new QgisSdkBridgeProtocolError(
			`${raw.subscription_id}: seq must be a non-negative integer`,
		);
	}
	const hasEvent = Object.hasOwn(raw, "event");
	const hasTerminal = Object.hasOwn(raw, "terminal");
	if (hasEvent === hasTerminal) {
		throw new QgisSdkBridgeProtocolError(
			`${raw.subscription_id}: a stream frame carries an event or a terminal, not both`,
		);
	}
	if (hasEvent) {
		if (!isPlainRecord(raw.event)) {
			throw new QgisSdkBridgeProtocolError(
				`${raw.subscription_id}: event must be an object`,
			);
		}
		const kind = raw.event.kind;
		if (!STREAM_EVENT_KINDS.includes(kind as StreamEventKind)) {
			throw new QgisSdkBridgeProtocolError(
				`${raw.subscription_id}: ${String(kind)} is not an event kind`,
			);
		}
		return Object.freeze({
			protocol: BRIDGE_PROTOCOL_VERSION,
			subscription_id: raw.subscription_id,
			seq: raw.seq,
			event: Object.freeze({
				kind: kind as StreamEventKind,
				payload: raw.event.payload,
			}),
		});
	}
	if (!isPlainRecord(raw.terminal)) {
		throw new QgisSdkBridgeProtocolError(
			`${raw.subscription_id}: terminal must be an object`,
		);
	}
	const kind = raw.terminal.kind;
	if (!TERMINAL_KINDS.includes(kind as StreamTerminalKind)) {
		throw new QgisSdkBridgeProtocolError(
			`${raw.subscription_id}: ${String(kind)} is not a terminal kind`,
		);
	}
	if (
		raw.terminal.message !== undefined &&
		typeof raw.terminal.message !== "string"
	) {
		throw new QgisSdkBridgeProtocolError(
			`${raw.subscription_id}: terminal.message must be a string`,
		);
	}
	if (raw.terminal.dropped !== undefined && !isIndex(raw.terminal.dropped)) {
		throw new QgisSdkBridgeProtocolError(
			`${raw.subscription_id}: terminal.dropped must be a non-negative integer`,
		);
	}
	return Object.freeze({
		protocol: BRIDGE_PROTOCOL_VERSION,
		subscription_id: raw.subscription_id,
		seq: raw.seq,
		terminal: Object.freeze({
			kind: kind as StreamTerminalKind,
			...(typeof raw.terminal.message === "string"
				? { message: raw.terminal.message }
				: {}),
			...(isIndex(raw.terminal.dropped)
				? { dropped: raw.terminal.dropped }
				: {}),
		}),
	});
}

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
