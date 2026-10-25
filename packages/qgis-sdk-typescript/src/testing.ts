/**
 * An injected per-client harness for the bridge (TASK-18, decision-23).
 *
 * The harness is a {@link WireTransport}: a page's own `BridgeClient` speaks to
 * it exactly as it would to a QWebChannel, and a test scripts what the host
 * answers - typed replies, faults, silence, stream events, terminals, gaps -
 * without touching a browser global or a running QGIS. Two harnesses are two
 * hosts, so isolation between clients is a fact a test can prove.
 *
 * What it proves is bounded. A green test here says the page handles the
 * frames a host *could* send; it says nothing about what a QWebEngineView or
 * a real host does. That evidence lives in the Python suite and in the
 * qualification harnesses recorded in doc-14. Keep the two apart in reports.
 *
 * Everything the harness sends is delivered asynchronously, one message per
 * microtask, so a reply never re-enters the client inside its own `send`.
 */

import type {
	BridgeStreamTerminal,
	StreamEventKind,
	WireTransport,
} from "./bridge";
import { QgisSdkError } from "./index";

const PROTOCOL = 1;
const SUBSCRIPTION_CAPACITY = 64;

/** A scripted host failure, returned from an expectation's handler. */
export interface ScriptedFault {
	readonly fault: { readonly code: string; readonly message: string };
}

/** Script a failure reply with this code and message. */
export function fault(code: string, message: string): ScriptedFault {
	return Object.freeze({ fault: Object.freeze({ code, message }) });
}

function isFault(value: unknown): value is ScriptedFault {
	return (
		typeof value === "object" &&
		value !== null &&
		"fault" in value &&
		typeof (value as ScriptedFault).fault === "object"
	);
}

/** Return this from a handler to never answer, so the client's timeout speaks. */
export const SILENCE: unique symbol = Symbol("qgis-sdk-harness-silence");

/** A subscription the script turns down: a fault reply, or no reply at all. */
export type ScriptedRefusal = ScriptedFault | typeof SILENCE;

/**
 * A subscribe expectation's script: emit on `stream` now or later, or return
 * a refusal instead of acknowledging.
 */
export type SubscribeScript<Req extends object> = (
	payload: Req,
	stream: ScriptedStream,
	// biome-ignore lint/suspicious/noConfusingVoidType: a script that only emits returns nothing
) => ScriptedRefusal | void;

/** What an invoke expectation may answer with. */
export type ScriptedReply<Res> =
	| Res
	| ScriptedFault
	| typeof SILENCE
	| Promise<Res | ScriptedFault | typeof SILENCE>;

/** A message the client sent, as the harness recorded it. */
export interface RecordedCall {
	readonly callId: string;
	readonly kind: "invoke" | "subscribe" | "unsubscribe";
	readonly operation: string;
	readonly payload?: Readonly<Record<string, unknown>>;
	readonly subscriptionId?: string;
}

/**
 * One scripted subscription. Frames carry the sequence the kernel checks, so
 * `skip` is the one way to script a gap.
 */
export interface ScriptedStream {
	readonly id: string;
	readonly operation: string;
	/** `false` once the host ended it or the page closed it. */
	readonly open: boolean;
	emit(kind: StreamEventKind, payload: unknown): void;
	end(terminal: BridgeStreamTerminal): void;
	/** Advance the sequence without sending, so the next frame is a gap. */
	skip(frames: number): void;
}

/** Options for a subscribe expectation. */
export interface SubscribeOptions {
	/** Delay the acknowledgement until this promise settles. */
	readonly ack?: () => Promise<void>;
}

/**
 * A test's script went wrong: an unmet or unexpected call, a leaked
 * subscription, a handler that threw, or an envelope that is not protocol 1.
 */
export class QgisSdkBridgeHarnessError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "harness_error");
	}
}

interface InvokeExpectation {
	readonly kind: "invoke";
	readonly operation: string;
	readonly handler: (payload: Readonly<Record<string, unknown>>) => unknown;
}

interface SubscribeExpectation {
	readonly kind: "subscribe";
	readonly operation: string;
	readonly script: SubscribeScript<Readonly<Record<string, unknown>>>;
	readonly options: SubscribeOptions;
}

type Expectation = InvokeExpectation | SubscribeExpectation;

interface OpenStream {
	readonly id: string;
	readonly operation: string;
	seq: number;
	open: boolean;
}

/** The harness a test holds; also the transport its client is built on. */
export interface BridgeHarness<Op extends string = string>
	extends WireTransport {
	/** Every message the client sent, in order. */
	readonly calls: readonly RecordedCall[];
	/** Calls no expectation covered; each was answered `unexpected_call`. */
	readonly unexpected: readonly RecordedCall[];
	/** Subscriptions neither ended by a script nor closed by the page. */
	readonly openSubscriptions: readonly string[];
	/** Clients currently attached. */
	readonly listeners: number;
	/** Answer the next `operation` call with what `handler` returns. */
	expectInvoke<
		Req extends object = Readonly<Record<string, unknown>>,
		Res = unknown,
	>(operation: Op, handler: (payload: Req) => ScriptedReply<Res>): void;
	/**
	 * Acknowledge the next `operation` subscription and hand `script` the
	 * stream; return a fault or {@link SILENCE} from it to refuse instead.
	 */
	expectSubscribe<Req extends object = Readonly<Record<string, unknown>>>(
		operation: Op,
		script: SubscribeScript<Req>,
		options?: SubscribeOptions,
	): void;
	/** Push any raw message, for what no expectation can script. */
	deliver(raw: unknown): void;
	/** Resolve once everything queued so far has been delivered. */
	settled(): Promise<void>;
	/** Throw unless every expectation was met and nothing leaked. */
	assertSatisfied(): void;
}

class Harness<Op extends string> implements BridgeHarness<Op> {
	private readonly listenerSet = new Set<(message: unknown) => void>();
	private readonly expectations: Expectation[] = [];
	private readonly recorded: RecordedCall[] = [];
	private readonly unexpectedCalls: RecordedCall[] = [];
	private readonly streams = new Map<string, OpenStream>();
	private readonly problems: string[] = [];
	private readonly outbox: unknown[] = [];
	private draining: Promise<void> | null = null;
	private streamCounter = 0;

	public get calls(): readonly RecordedCall[] {
		return [...this.recorded];
	}

	public get unexpected(): readonly RecordedCall[] {
		return [...this.unexpectedCalls];
	}

	public get openSubscriptions(): readonly string[] {
		return [...this.streams.values()]
			.filter((stream) => stream.open)
			.map((stream) => stream.id);
	}

	public get listeners(): number {
		return this.listenerSet.size;
	}

	public subscribe(listener: (message: unknown) => void): () => void {
		this.listenerSet.add(listener);
		return () => {
			this.listenerSet.delete(listener);
			if (this.listenerSet.size === 0) {
				// The last client detached: the view is gone, and a host disposes
				// the subscriptions of a view it lost (decision-23), so they are
				// no longer leaks.
				for (const stream of this.streams.values()) {
					stream.open = false;
				}
			}
		};
	}

	public send(message: unknown): void {
		const envelope = this.parseEnvelope(message);
		if (envelope.kind === "unsubscribe") {
			this.closeFromPage(envelope);
			return;
		}
		const expectation = this.take(envelope.kind, envelope.operation);
		if (expectation === undefined) {
			this.unexpectedCalls.push(envelope);
			this.deliverFailure(
				envelope.callId,
				"unexpected_call",
				`no expectation covers ${envelope.kind} ${JSON.stringify(envelope.operation)}`,
			);
			return;
		}
		if (expectation.kind === "invoke") {
			this.answerInvoke(envelope, expectation);
			return;
		}
		this.answerSubscribe(envelope, expectation);
	}

	public expectInvoke<Req extends object, Res>(
		operation: Op,
		handler: (payload: Req) => ScriptedReply<Res>,
	): void {
		this.expectations.push({
			kind: "invoke",
			operation,
			handler: handler as InvokeExpectation["handler"],
		});
	}

	public expectSubscribe<Req extends object>(
		operation: Op,
		script: SubscribeScript<Req>,
		options: SubscribeOptions = {},
	): void {
		this.expectations.push({
			kind: "subscribe",
			operation,
			script: script as SubscribeExpectation["script"],
			options,
		});
	}

	public deliver(raw: unknown): void {
		this.outbox.push(raw);
		this.drain();
	}

	public settled(): Promise<void> {
		return this.draining ?? Promise.resolve();
	}

	public assertSatisfied(): void {
		const problems = [...this.problems];
		if (this.expectations.length > 0) {
			const unmet = this.expectations.map(
				(expectation) => `${expectation.kind} ${expectation.operation}`,
			);
			problems.push(`unmet expectations: ${unmet.join(", ")}`);
		}
		if (this.unexpectedCalls.length > 0) {
			const unexpected = this.unexpectedCalls.map(
				(call) => `${call.kind} ${call.operation}`,
			);
			problems.push(`unexpected calls: ${unexpected.join(", ")}`);
		}
		const open = this.openSubscriptions;
		if (open.length > 0) {
			problems.push(`open subscriptions: ${open.join(", ")}`);
		}
		if (problems.length > 0) {
			throw new QgisSdkBridgeHarnessError(problems.join("; "));
		}
	}

	// -- answering ---------------------------------------------------------------

	private answerInvoke(
		call: RecordedCall,
		expectation: InvokeExpectation,
	): void {
		this.resolveHandler(call, () =>
			expectation.handler(call.payload ?? {}),
		).then((reply) => {
			if (reply === SILENCE) {
				return;
			}
			if (isFault(reply)) {
				this.deliverFailure(call.callId, reply.fault.code, reply.fault.message);
				return;
			}
			this.deliver({
				protocol: PROTOCOL,
				call_id: call.callId,
				ok: true,
				value: reply,
			});
		});
	}

	private answerSubscribe(
		call: RecordedCall,
		expectation: SubscribeExpectation,
	): void {
		this.streamCounter += 1;
		const open: OpenStream = {
			id: `s${this.streamCounter}`,
			operation: call.operation,
			seq: 0,
			open: false,
		};
		// Frames the script emits before the acknowledgement is decided are held
		// back: a refused subscription sends none, an accepted one sends them
		// after the acknowledgement, so the kernel has registered the
		// subscription by the time the first frame reaches it.
		const held: unknown[] = [];
		let sink = (frame: unknown): void => {
			held.push(frame);
		};
		const stream = this.scripted(open, (frame) => sink(frame));
		const ack = expectation.options.ack ?? (() => Promise.resolve());
		ack()
			.then(() =>
				this.resolveHandler(call, () => {
					open.open = true;
					return expectation.script(call.payload ?? {}, stream);
				}),
			)
			.then((outcome) => {
				if (outcome === SILENCE || isFault(outcome)) {
					open.open = false;
					held.length = 0;
					if (isFault(outcome)) {
						this.deliverFailure(
							call.callId,
							outcome.fault.code,
							outcome.fault.message,
						);
					}
					return;
				}
				if (this.listenerSet.size === 0) {
					// The view detached while the host was deciding: nothing to
					// acknowledge to, nothing to keep open.
					open.open = false;
					held.length = 0;
					return;
				}
				this.streams.set(open.id, open);
				this.deliver({
					protocol: PROTOCOL,
					call_id: call.callId,
					ok: true,
					value: {
						subscription_id: open.id,
						capacity: SUBSCRIPTION_CAPACITY,
					},
				});
				sink = (frame) => this.deliver(frame);
				for (const frame of held) {
					sink(frame);
				}
				held.length = 0;
			});
	}

	private resolveHandler(
		call: RecordedCall,
		run: () => unknown,
	): Promise<unknown> {
		return new Promise<unknown>((resolve) => {
			resolve(run());
		}).catch((error: unknown) => {
			const message = error instanceof Error ? error.message : String(error);
			this.problems.push(
				`handler for ${call.kind} ${call.operation} threw: ${message}`,
			);
			return fault("harness_error", message);
		});
	}

	private scripted(
		open: OpenStream,
		sink: (frame: unknown) => void,
	): ScriptedStream {
		const requireOpen = (verb: string): void => {
			if (!open.open) {
				throw new QgisSdkBridgeHarnessError(
					`cannot ${verb} on subscription ${open.id}: it is not open`,
				);
			}
		};
		return {
			id: open.id,
			operation: open.operation,
			get open(): boolean {
				return open.open;
			},
			emit: (kind, payload) => {
				requireOpen("emit");
				sink({
					protocol: PROTOCOL,
					subscription_id: open.id,
					seq: open.seq,
					event: { kind, payload },
				});
				open.seq += 1;
			},
			end: (terminal) => {
				requireOpen("end");
				open.open = false;
				sink({
					protocol: PROTOCOL,
					subscription_id: open.id,
					seq: open.seq,
					terminal,
				});
				open.seq += 1;
			},
			skip: (frames) => {
				requireOpen("skip");
				open.seq += frames;
			},
		};
	}

	private closeFromPage(call: RecordedCall): void {
		const open =
			call.subscriptionId === undefined
				? undefined
				: this.streams.get(call.subscriptionId);
		const disposed = open?.open === true;
		if (open !== undefined) {
			open.open = false;
		}
		this.deliver({
			protocol: PROTOCOL,
			call_id: call.callId,
			ok: true,
			value: { disposed },
		});
	}

	private deliverFailure(callId: string, code: string, message: string): void {
		this.deliver({
			protocol: PROTOCOL,
			call_id: callId,
			ok: false,
			error: { code, message },
		});
	}

	private drain(): void {
		if (this.draining !== null) {
			return;
		}
		this.draining = (async () => {
			while (this.outbox.length > 0) {
				await Promise.resolve();
				const message = this.outbox.shift();
				for (const listener of [...this.listenerSet]) {
					listener(message);
				}
			}
			this.draining = null;
		})();
	}

	// -- parsing -------------------------------------------------------------------

	private take(
		kind: "invoke" | "subscribe",
		operation: string,
	): Expectation | undefined {
		const index = this.expectations.findIndex(
			(expectation) =>
				expectation.kind === kind && expectation.operation === operation,
		);
		if (index === -1) {
			return undefined;
		}
		return this.expectations.splice(index, 1)[0];
	}

	private parseEnvelope(message: unknown): RecordedCall {
		if (typeof message !== "object" || message === null) {
			throw new QgisSdkBridgeHarnessError("the client sent a non-object");
		}
		const raw = message as Record<string, unknown>;
		if (raw.protocol !== PROTOCOL) {
			throw new QgisSdkBridgeHarnessError(
				`the client speaks protocol ${String(raw.protocol)}; the harness fakes ${PROTOCOL}`,
			);
		}
		if (typeof raw.call_id !== "string" || raw.call_id.length === 0) {
			throw new QgisSdkBridgeHarnessError("the client sent no call_id");
		}
		const callId = raw.call_id;
		if (raw.kind === "unsubscribe") {
			const subscriptionId = raw.subscription_id;
			if (typeof subscriptionId !== "string") {
				throw new QgisSdkBridgeHarnessError(
					`${callId}: unsubscribe names no subscription_id`,
				);
			}
			const call: RecordedCall = {
				callId,
				kind: "unsubscribe",
				operation: this.streams.get(subscriptionId)?.operation ?? "",
				subscriptionId,
			};
			this.recorded.push(call);
			return call;
		}
		if (raw.kind !== "invoke" && raw.kind !== "subscribe") {
			throw new QgisSdkBridgeHarnessError(
				`${callId}: ${String(raw.kind)} is not a bridge envelope kind`,
			);
		}
		if (typeof raw.operation !== "string") {
			throw new QgisSdkBridgeHarnessError(
				`${callId}: operation must be a string`,
			);
		}
		const payload =
			typeof raw.payload === "object" && raw.payload !== null
				? (raw.payload as Readonly<Record<string, unknown>>)
				: {};
		const call: RecordedCall = {
			callId,
			kind: raw.kind,
			operation: raw.operation,
			payload,
		};
		this.recorded.push(call);
		return call;
	}
}

/**
 * Create a harness; `Op` narrows the operations a test may expect, typically
 * the generated module's `OperationId`.
 */
export function createBridgeHarness<
	Op extends string = string,
>(): BridgeHarness<Op> {
	return new Harness<Op>();
}
