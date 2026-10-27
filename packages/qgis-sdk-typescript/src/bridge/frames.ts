/** Parsing one invoke reply and one stream frame, refusing what the host could not send. */

import type { StreamEventKind } from "../declarations";
import { isPlainRecord, STREAM_EVENT_KINDS } from "../internal";
import { QgisSdkBridgeProtocolError } from "./errors";
import {
	BRIDGE_PROTOCOL_VERSION,
	type BridgeStreamFrame,
	type InvokeReply,
	MAX_CALL_ID_LENGTH,
	type StreamTerminalKind,
} from "./protocol";

export function isNonEmptyString(value: unknown): value is string {
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
