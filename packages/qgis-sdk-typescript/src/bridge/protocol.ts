/** The wire shapes of the bridge protocol: replies, frames, transport and options. */

import type { StreamEventKind } from "../declarations";

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
