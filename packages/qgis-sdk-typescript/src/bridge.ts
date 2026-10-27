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

export type { BridgeSubscription, SubscriptionHandlers } from "./bridge/client";
export { BridgeClient } from "./bridge/client";
export {
	QgisSdkBridgeAbortedError,
	QgisSdkBridgeClosedError,
	QgisSdkBridgeProtocolError,
	QgisSdkBridgeRemoteError,
	QgisSdkBridgeSequenceError,
	QgisSdkBridgeStreamEndedError,
	QgisSdkBridgeTimeoutError,
} from "./bridge/errors";
export { parseInvokeReply, parseStreamFrame } from "./bridge/frames";
export type {
	BridgeClientOptions,
	BridgeEventFrame,
	BridgeFailure,
	BridgeStreamEvent,
	BridgeStreamFrame,
	BridgeStreamTerminal,
	BridgeTerminalFrame,
	InvokeOptions,
	InvokeReply,
	StreamTerminalKind,
	WireTransport,
} from "./bridge/protocol";
export { BRIDGE_PROTOCOL_VERSION, MAX_CALL_ID_LENGTH } from "./bridge/protocol";
export type { StreamEventKind };
