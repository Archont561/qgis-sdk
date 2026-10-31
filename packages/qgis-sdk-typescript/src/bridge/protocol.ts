/** The wire shapes of the bridge protocol: replies, frames, transport and options. */

import type { StreamEventKind } from "../declarations";

/**
 * The wire protocol this client speaks.
 *
 * Version 2 added `kind: "ack"`: a client acknowledges every stream frame it
 * delivered, and the host keeps a bounded number of them in flight so a slow
 * consumer slows the producer instead of filling a queue (decision-59).
 */
export const BRIDGE_PROTOCOL_VERSION: 2 = 2;

/** The protocol version as a type, so one constant moves every shape below. */
export type ProtocolVersion = typeof BRIDGE_PROTOCOL_VERSION;

export const MAX_CALL_ID_LENGTH: number = 128;

/** A failure reply, as the host serialized it. */
export interface BridgeFailure {
	readonly code: string;
	readonly message: string;
}

/** A reply to one invocation: exactly one of `value` or `error` is present. */
export type InvokeReply =
	| {
			readonly protocol: ProtocolVersion;
			readonly call_id: string;
			readonly ok: true;
			readonly value: unknown;
	  }
	| {
			readonly protocol: ProtocolVersion;
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
	readonly protocol: ProtocolVersion;
	readonly subscription_id: string;
	readonly seq: number;
	readonly event: BridgeStreamEvent;
}

/** The frame that ends a subscription. */
export interface BridgeTerminalFrame {
	readonly protocol: ProtocolVersion;
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
	/**
	 * Acknowledge every stream frame on delivery. On by default: without an
	 * acknowledgement the host cannot tell a slow consumer from a dead one, and
	 * stops at a bounded queue instead of applying backpressure.
	 */
	readonly acknowledge?: boolean;
}

/** One blob chunk, as `blob.get` returns it. */
export interface BlobChunk {
	readonly offset: number;
	readonly length: number;
	readonly size: number;
	readonly media_type: string;
	readonly checksum: string;
	readonly data_base64: string;
	readonly next_offset: number | null;
}

/** Options for one invocation. */
export interface InvokeOptions {
	readonly signal?: AbortSignal;
}
