/**
 * The versioned transport contract a web view speaks (TASK-4, first slice).
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

import { QgisSdkError } from "./index";

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

function isPlainRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
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
	if (!isNonEmptyString(raw.call_id) || raw.call_id.length > MAX_CALL_ID_LENGTH) {
		throw new QgisSdkBridgeProtocolError(
			`call_id must be a nonempty string of at most ${MAX_CALL_ID_LENGTH} characters`,
		);
	}
	const callId = raw.call_id;
	if (typeof raw.ok !== "boolean") {
		throw new QgisSdkBridgeProtocolError(
			`${callId}: ok must be a boolean`,
		);
	}
	if (raw.ok) {
		if (!Object.prototype.hasOwnProperty.call(raw, "value")) {
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
		throw new QgisSdkBridgeProtocolError(`${callId}: error.code must be a string`);
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
	private readonly unsubscribe: () => void;
	private counter: number = 0;
	private closed: boolean = false;
	private unmatched: number = 0;
	private lastProtocolError: Error | null = null;

	public constructor(transport: WireTransport, options: BridgeClientOptions = {}) {
		this.transport = transport;
		this.timeoutMs = options.timeoutMs ?? 30_000;
		this.unsubscribe = transport.subscribe((message) => {
			this.handle(message);
		});
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
		if (this.closed) {
			return Promise.reject(new QgisSdkBridgeClosedError());
		}
		if (!isNonEmptyString(operation)) {
			return Promise.reject(
				new QgisSdkBridgeProtocolError("operation must be a nonempty string"),
			);
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
							pending.reject(new QgisSdkBridgeTimeoutError(callId, this.timeoutMs));
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
				operation,
				payload,
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

	/** The last malformed message this client refused, if any. */
	public get protocolError(): Error | null {
		return this.lastProtocolError;
	}
}
