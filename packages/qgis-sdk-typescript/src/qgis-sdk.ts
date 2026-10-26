/**
 * `QgisSdk`: the page-side object a plugin's web view talks to QGIS through.
 *
 * Three statements connect a page (decision-44):
 *
 * ```ts
 * import schema from "./bridge.schema";
 * const qgis = QgisSdk.fromBridgeSchema(schema);
 * await qgis.sites.summary({ layer_id });
 * ```
 *
 * The schema is the generated `bridge.schema.ts`: the plugin description plus
 * its `Operations` and `Streams` types. From the description the SDK builds
 * one method per declared action and stream, nested under the segments of its
 * id (`sites.summary` is `qgis.sites.summary`, `buffer` is `qgis.buffer`),
 * and checks every argument, reply and event against the declared schemas
 * with the same rules the host applies (`validate.ts`). From the types it gives those
 * methods their signatures, so a wrong argument shape or an unknown operation
 * is a compile error and a value outside the schema at run time is a
 * {@link QgisSdkContractError}.
 *
 * `host` is the curated host surface of decision-27, built on the same client,
 * plus `granted`: the host operation ids the handshake advertised for this
 * view. A call outside the grants is not refused here - the host refuses it,
 * and the page sees the host's `not_authorized` - but a page can read `granted`
 * after `ready` to hide what it may not use.
 */

import {
	BridgeClient,
	type BridgeStreamTerminal,
	type BridgeSubscription,
	type InvokeOptions,
	QgisSdkBridgeProtocolError,
	type WireTransport,
} from "./bridge";
import {
	type ActionDescription,
	QgisSdkDeclarationError,
	type StreamDescription,
} from "./declarations";
import {
	createHost,
	HOST_OPERATIONS,
	type HostOperationId,
	type HostOperations,
} from "./generated/host";
import { isPlainRecord } from "./internal";
import type {
	BridgeSchema,
	OperationMap,
	OperationShape,
	StreamMap,
	StreamShape,
} from "./schema";
import { QgisSdkContractError, validateAgainstSchema } from "./validate";
import { createWebChannelTransport } from "./webchannel";

/** Options for {@link QgisSdk.fromBridgeSchema}. */
export interface QgisSdkOptions {
	/** A transport to speak through; defaults to the page's QWebChannel. */
	readonly transport?: WireTransport;
	/** A client the caller owns; `close()` leaves it open. Excludes `transport`. */
	readonly client?: BridgeClient;
	/** Per-call timeout for an owned client. */
	readonly timeoutMs?: number;
	/** The channel object's name when the default transport is used. */
	readonly channelObject?: string;
}

/** Handlers for a typed stream: events as declared, then exactly one end. */
export interface StreamHandlers<E> {
	readonly onEvent?: (event: E) => void;
	readonly onTerminal?: (terminal: BridgeStreamTerminal) => void;
}

/** A live stream, as the caller holds it. */
export type StreamHandle = BridgeSubscription;

/** The method one declared action becomes; an empty request may be omitted. */
export type OperationMethod<Op extends OperationShape> =
	// biome-ignore lint/complexity/noBannedTypes: `{}` is the test for "nothing required"
	{} extends Op["request"]
		? (
				request?: Op["request"],
				options?: InvokeOptions,
			) => Promise<Op["result"]>
		: (
				request: Op["request"],
				options?: InvokeOptions,
			) => Promise<Op["result"]>;

/** The method one declared stream becomes. */
export type StreamMethod<St extends StreamShape> = (
	request: St["request"],
	handlers: StreamHandlers<St["event"]>,
	options?: InvokeOptions,
) => Promise<StreamHandle>;

/** What the handshake told this page about the host (decision-27). */
export interface QgisSdkHost extends HostOperations {
	/**
	 * The host operation ids the handshake advertised for this view; empty
	 * until {@link QgisSdkCore.ready} has resolved.
	 */
	readonly granted: readonly HostOperationId[];
}

/** The members every `QgisSdk` has, whatever its schema declares. */
export interface QgisSdkCore<O = OperationMap, S = StreamMap> {
	/** The schema this instance was built from. */
	readonly schema: BridgeSchema<O, S>;
	/** The client under the methods, for what a method does not cover. */
	readonly client: BridgeClient;
	/** The curated host surface, and what this view was granted of it. */
	readonly host: QgisSdkHost;
	/** Resolves once the handshake answered; rejects when the host refused it. */
	readonly ready: Promise<void>;
	/** Close an owned client; a client the caller passed in is left alone. */
	close(): void;
}

/** The first segment of a dotted id, or the whole id when it has none. */
type Head<K extends string> = K extends `${infer H}.${string}` ? H : K;

/** The members of `M` under one head, keyed by the rest of their ids. */
type Under<M, H extends string> = {
	[K in keyof M & string as K extends `${H}.${infer Rest}`
		? Rest
		: never]: M[K];
};

/**
 * The declared actions as a tree: a plain id is a method, a dotted id nests
 * one object per segment. An id that is both a leaf and a prefix of another
 * is refused at run time, so the type need not say what it would mean.
 */
export type OperationTree<O> = {
	readonly [H in Head<keyof O & string>]: H extends keyof O
		? O[H] extends OperationShape
			? OperationMethod<O[H]>
			: never
		: OperationTree<Under<O, H>>;
};

/** The declared streams as the same tree, with a stream method at each leaf. */
export type StreamTree<S> = {
	readonly [H in Head<keyof S & string>]: H extends keyof S
		? S[H] extends StreamShape
			? StreamMethod<S[H]>
			: never
		: StreamTree<Under<S, H>>;
};

/**
 * A page's handle on QGIS: the core, plus one method per declared operation
 * nested under the segments of its id.
 */
export type QgisSdk<O = OperationMap, S = StreamMap> = QgisSdkCore<O, S> &
	OperationTree<O> &
	StreamTree<S>;

/** Names {@link QgisSdkCore} keeps; a declared id may not start with one. */
export const QGIS_SDK_MEMBERS: readonly string[] = Object.freeze([
	"client",
	"host",
	"schema",
	"ready",
	"close",
]);

const HOST_IDS: ReadonlySet<string> = new Set<string>(HOST_OPERATIONS);

/** The handshake, as far as this module reads it. */
interface Handshake {
	readonly operations: readonly string[];
}

function parseHandshake(value: unknown): Handshake {
	if (!isPlainRecord(value) || !Array.isArray(value.operations)) {
		throw new QgisSdkBridgeProtocolError(
			"The handshake reply carries no operations list",
		);
	}
	const operations: string[] = [];
	for (const operation of value.operations) {
		if (isPlainRecord(operation) && typeof operation.id === "string") {
			operations.push(operation.id);
		}
	}
	return { operations };
}

function unwrapRequest(
	operation: string,
	request: unknown,
): Record<string, unknown> {
	if (request === undefined) {
		return {};
	}
	if (!isPlainRecord(request)) {
		throw new QgisSdkContractError(operation, "request", [
			...validateAgainstSchema(request, { type: "object" }),
		]);
	}
	return request;
}

function checkedRequest(
	description: ActionDescription | StreamDescription,
	request: unknown,
): Record<string, unknown> {
	const payload = unwrapRequest(description.id, request);
	const issues = validateAgainstSchema(payload, description.request);
	if (issues.length > 0) {
		throw new QgisSdkContractError(description.id, "request", issues);
	}
	return payload;
}

function operationMethod(
	client: BridgeClient,
	action: ActionDescription,
): (request?: unknown, options?: InvokeOptions) => Promise<unknown> {
	return async (request, options) => {
		const payload = checkedRequest(action, request);
		const value = await client.invoke(action.id, payload, options);
		const issues = validateAgainstSchema(value, action.result, {
			allowUnknown: true,
		});
		if (issues.length > 0) {
			throw new QgisSdkContractError(action.id, "result", issues);
		}
		return value;
	};
}

function streamMethod(
	client: BridgeClient,
	stream: StreamDescription,
): (
	request: unknown,
	handlers: StreamHandlers<unknown>,
	options?: InvokeOptions,
) => Promise<StreamHandle> {
	return async (request, handlers, options) => {
		const payload = checkedRequest(stream, request);
		// The typed stream ends exactly once, like the subscription under it: a
		// contract violation ends it here, closes the subscription, and the
		// `disposed` the client then reports is not delivered a second time.
		let ended = false;
		let violated = false;
		let handle: StreamHandle | null = null;
		const end = (terminal: BridgeStreamTerminal): void => {
			if (ended) {
				return;
			}
			ended = true;
			handlers.onTerminal?.(terminal);
		};
		handle = await client.subscribe(
			stream.id,
			payload,
			{
				onEvent: (event) => {
					if (ended) {
						return;
					}
					const declared = stream.events[event.kind];
					const issues =
						declared === undefined
							? undefined
							: validateAgainstSchema(event.payload, declared, {
									allowUnknown: true,
									path: ["payload"],
								});
					if (issues !== undefined && issues.length === 0) {
						handlers.onEvent?.(event);
						return;
					}
					const error = new QgisSdkContractError(
						stream.id,
						"event",
						issues ?? [],
					);
					end({ kind: "error", message: error.message });
					if (handle === null) {
						violated = true;
					} else {
						handle.close();
					}
				},
				onTerminal: end,
			},
			options,
		);
		if (violated) {
			handle.close();
		}
		return handle;
	};
}

function buildHost(
	client: BridgeClient,
	granted: () => readonly HostOperationId[],
): QgisSdkHost {
	const host = createHost(client);
	return Object.freeze({
		...host,
		get granted(): readonly HostOperationId[] {
			return granted();
		},
	});
}

function build<O, S>(
	schema: BridgeSchema<O, S>,
	options: QgisSdkOptions,
): QgisSdk<O, S> {
	if (options.client !== undefined && options.transport !== undefined) {
		throw new QgisSdkDeclarationError(
			"QgisSdk.fromBridgeSchema takes a client or a transport, not both",
		);
	}
	const owned = options.client === undefined;
	const transport =
		options.transport ??
		(options.client === undefined
			? createWebChannelTransport(options.channelObject ?? "bridge")
			: undefined);
	const client =
		options.client ??
		new BridgeClient(
			transport as WireTransport,
			options.timeoutMs === undefined ? {} : { timeoutMs: options.timeoutMs },
		);
	let granted: readonly HostOperationId[] = Object.freeze([]);
	const ready = client.handshake().then((value) => {
		const handshake = parseHandshake(value);
		granted = Object.freeze(
			handshake.operations.filter((id): id is HostOperationId =>
				HOST_IDS.has(id),
			),
		);
	});
	// A page that never awaits `ready` still sees every call fail on its own;
	// the rejection is not left unobserved on top of that.
	ready.catch(() => undefined);
	const members: Record<string, unknown> = {
		schema,
		client,
		host: buildHost(client, () => granted),
		ready,
		close: (): void => {
			if (owned) {
				client.close();
			}
		},
	};
	const namespaces: Record<string, unknown>[] = [];
	for (const action of schema.actions) {
		place(members, namespaces, action.id, operationMethod(client, action));
	}
	for (const stream of schema.streams) {
		place(members, namespaces, stream.id, streamMethod(client, stream));
	}
	for (const namespace of namespaces) {
		Object.freeze(namespace);
	}
	return Object.freeze(members) as unknown as QgisSdk<O, S>;
}

/**
 * Put one method where its id says: `a.b.c` becomes `members.a.b.c`, building
 * the objects on the way. Two ids cannot both be honest when one is a prefix
 * of the other - `sites` cannot be a method and hold `sites.summary` - and a
 * first segment that is a core member would hide it, so both are refused.
 */
function place(
	members: Record<string, unknown>,
	namespaces: Record<string, unknown>[],
	id: string,
	method: unknown,
): void {
	const segments = id.split(".");
	if (segments.some((segment) => segment === "")) {
		throw new QgisSdkDeclarationError(
			`${id}: an operation id may not have an empty segment`,
		);
	}
	const head = segments[0] as string;
	if (QGIS_SDK_MEMBERS.includes(head)) {
		throw new QgisSdkDeclarationError(
			`${id}: an operation id may not start with a QgisSdk member (${QGIS_SDK_MEMBERS.join(", ")})`,
		);
	}
	let node = members;
	for (const [index, segment] of segments.entries()) {
		const prefix = segments.slice(0, index + 1).join(".");
		const existing = node[segment];
		if (index === segments.length - 1) {
			if (existing !== undefined) {
				throw new QgisSdkDeclarationError(
					typeof existing === "function"
						? `${id}: duplicate operation id`
						: `${id}: an operation id may not be a prefix of another declared id`,
				);
			}
			node[segment] = method;
			return;
		}
		if (existing === undefined) {
			const namespace: Record<string, unknown> = {};
			namespaces.push(namespace);
			node[segment] = namespace;
			node = namespace;
		} else if (typeof existing === "function") {
			throw new QgisSdkDeclarationError(
				`${id}: ${prefix} is already an operation id; an id may not extend another`,
			);
		} else {
			node = existing as Record<string, unknown>;
		}
	}
}

/**
 * The entry point: `QgisSdk.fromBridgeSchema(schema)`.
 *
 * A namespace rather than a constant so the value and the instance type share
 * one name through every declaration bundler.
 */
export namespace QgisSdk {
	/**
	 * Build a `QgisSdk` on a generated schema.
	 *
	 * Without options it connects to the page's QWebChannel object named
	 * "bridge", which is what the Python runtime registers; a test passes the
	 * harness from `@archont561/qgis-sdk/testing` as `transport` instead.
	 */
	export function fromBridgeSchema<
		O extends Record<keyof O, OperationShape>,
		S extends Record<keyof S, StreamShape>,
	>(schema: BridgeSchema<O, S>, options: QgisSdkOptions = {}): QgisSdk<O, S> {
		return build(schema, options);
	}
}
