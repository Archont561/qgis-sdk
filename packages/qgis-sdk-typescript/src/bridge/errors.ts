/** The bridge's errors: protocol, timeout, abort, closed, sequence, ended and remote. */

import { QgisSdkError } from "../errors";
import type { BridgeFailure, BridgeStreamTerminal } from "./protocol";

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
