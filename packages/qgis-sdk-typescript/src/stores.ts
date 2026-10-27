/**
 * The framework-free store core (decision-47).
 *
 * Every adapter - `./react`, `./vue`, `./svelte`, or a vanilla page with no
 * adapter at all - drives the same four stores. A store is a value plus the
 * Svelte store contract: `subscribe(listener)` calls the listener at once with
 * the current snapshot and again after every change, and returns the
 * unsubscribe function; `getSnapshot()` is the same value without a
 * subscription, kept referentially stable between changes so React's
 * `useSyncExternalStore` can compare it. Nothing in this module imports a
 * framework, touches the DOM or runs at import time.
 *
 * - {@link OperationStore} runs one generated operation: the latest run wins,
 *   an aborted call is swallowed, and `run` never rejects into a handler.
 * - {@link StreamStore} holds one generated stream open while its input is
 *   non-null, reopening only when the input's *content* changes.
 * - {@link FormStore} binds the values of one declared action's request to its
 *   schema: fields from the declaration, issues from the validator, submission
 *   through an operation store.
 * - {@link HostQueryStore} reads the curated host surface and says `refused`
 *   - before any call leaves the page - when the view was not granted the
 *   operation it needs.
 */

import { QgisSdkBridgeAbortedError } from "./bridge";
import type { ActionDescription, QgisSdkValidationIssue } from "./declarations";
import { QgisSdkError } from "./errors";
import type {
	HostOperationId,
	LayerPage,
	VectorLayerInfo,
} from "./generated/host";
import { isPlainRecord } from "./internal";
import type { QgisSdkCore, QgisSdkHost } from "./qgis-sdk";
import type { OperationShape } from "./schema";
import { type DeclaredSchema, validateAgainstSchema } from "./validate";

/** A store was built or driven outside the shape it needs. */
export class QgisSdkStoreError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "store_binding");
	}
}

// ---------------------------------------------------------------------------
// The contract
// ---------------------------------------------------------------------------

/** What a listener receives: the whole snapshot, never a diff. */
export type StoreListener<T> = (snapshot: T) => void;

/**
 * The contract every store honours, and the one `useSyncExternalStore`,
 * Vue's `shallowRef` wiring and Svelte's `$store` all read.
 */
export interface Store<T> {
	/** The current value; the same object until the next change. Bound. */
	readonly getSnapshot: () => T;
	/**
	 * Call `listener` now and after every change; the returned function
	 * stops the calls. Bound. Svelte passes a second `invalidate` argument,
	 * which is ignored.
	 */
	readonly subscribe: (listener: StoreListener<T>) => () => void;
}

abstract class BaseStore<T> implements Store<T> {
	private snapshot: T;
	private readonly listeners = new Set<StoreListener<T>>();

	protected constructor(initial: T) {
		this.snapshot = initial;
	}

	// Bound, so `useSyncExternalStore(store.subscribe, store.getSnapshot)`
	// needs no wrapper.
	public readonly getSnapshot = (): T => this.snapshot;

	public readonly subscribe = (listener: StoreListener<T>): (() => void) => {
		this.listeners.add(listener);
		listener(this.snapshot);
		return () => {
			this.listeners.delete(listener);
		};
	};

	protected publish(next: T): void {
		if (Object.is(next, this.snapshot)) {
			return;
		}
		this.snapshot = next;
		for (const listener of [...this.listeners]) {
			listener(next);
		}
	}
}

function asError(error: unknown): Error {
	return error instanceof Error ? error : new Error(String(error));
}

// ---------------------------------------------------------------------------
// OperationStore
// ---------------------------------------------------------------------------

/** Where one invocation stands. */
export type OperationState<R> =
	| { readonly status: "idle" }
	| { readonly status: "pending" }
	| { readonly status: "ok"; readonly value: R }
	| { readonly status: "error"; readonly error: Error };

/** An operation member of a generated map: input, optional signal, promise. */
export type Operation<I, R> = (
	input: I,
	options?: { readonly signal?: AbortSignal },
) => Promise<R>;

const IDLE: OperationState<never> = Object.freeze({ status: "idle" });
const PENDING: OperationState<never> = Object.freeze({ status: "pending" });

/**
 * Run one generated operation.
 *
 * `run` resolves with the value, or with `undefined` when the call failed,
 * was aborted or was superseded by a later run - the state carries the error,
 * so the promise never rejects into an event handler. Only the latest run can
 * change the state. `abort` ends the in-flight call locally (the host may
 * still run it); `reset` aborts and returns to `idle`. The methods are bound,
 * so they can be passed around without the store.
 */
export class OperationStore<I, R> extends BaseStore<OperationState<R>> {
	private generation = 0;
	private controller: AbortController | null = null;

	public constructor(private readonly operation: Operation<I, R>) {
		super(IDLE);
	}

	public readonly abort = (): void => {
		this.generation += 1;
		this.controller?.abort();
		this.controller = null;
	};

	public readonly reset = (): void => {
		this.abort();
		this.publish(IDLE);
	};

	public readonly run = async (input: I): Promise<R | undefined> => {
		this.abort();
		const mine = this.generation;
		const controller = new AbortController();
		this.controller = controller;
		this.publish(PENDING);
		try {
			const value = await this.operation(input, { signal: controller.signal });
			if (this.generation !== mine) {
				return undefined;
			}
			this.publish({ status: "ok", value });
			return value;
		} catch (error) {
			if (
				this.generation !== mine ||
				error instanceof QgisSdkBridgeAbortedError
			) {
				return undefined;
			}
			this.publish({ status: "error", error: asError(error) });
			return undefined;
		} finally {
			if (this.controller === controller) {
				this.controller = null;
			}
		}
	};
}

// ---------------------------------------------------------------------------
// StreamStore
// ---------------------------------------------------------------------------

/** How a stream ended, as the generated module reports it. */
export interface StreamTerminalLike {
	readonly kind: string;
	readonly message?: string;
	readonly dropped?: number;
}

/** The handle a generated stream member resolves with. */
export interface StreamHandleLike {
	readonly id: string;
	readonly closed: boolean;
	close(): void;
}

/** Handlers for a stream, as a generated module types them. */
export interface StreamHandlersLike<E> {
	readonly onEvent?: (event: E) => void;
	readonly onTerminal?: (terminal: StreamTerminalLike) => void;
}

/** A stream member of a generated map. */
export type Stream<I, E> = (
	input: I,
	handlers: StreamHandlersLike<E>,
	options?: { readonly signal?: AbortSignal },
) => Promise<StreamHandleLike>;

/** Where one subscription stands. */
export interface StreamState<E> {
	/** `idle` with a null input, `failed` when the host refused to open it. */
	readonly status: "idle" | "opening" | "open" | "ended" | "failed";
	readonly lastEvent: E | null;
	readonly terminal: StreamTerminalLike | null;
	readonly error: Error | null;
}

const IDLE_STREAM: StreamState<never> = Object.freeze({
	status: "idle",
	lastEvent: null,
	terminal: null,
	error: null,
});

/**
 * Return a key that is equal for two inputs with the same content, whatever
 * the order their fields were written in.
 */
export function stableKey(value: unknown): string {
	return JSON.stringify(value, (_key, item: unknown) =>
		isPlainRecord(item)
			? Object.fromEntries(
					Object.entries(item).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
				)
			: item,
	);
}

/**
 * Hold one generated stream open while its input is non-null.
 *
 * `setInput` follows the *content* of the input: a new object with the same
 * fields changes nothing, a different one closes the old stream and opens a
 * new one, `null` closes it. Handlers are read fresh on every frame, so
 * `setHandlers` with a new closure reopens nothing. `close` is safe before the
 * host has acknowledged the stream: the handle is closed the moment it
 * arrives.
 */
export class StreamStore<I, E> extends BaseStore<StreamState<E>> {
	private key: string | null = null;
	private cancel: (() => void) | null = null;

	public constructor(
		private readonly open: Stream<I, E>,
		private handlers: StreamHandlersLike<E> = {},
	) {
		super(IDLE_STREAM);
	}

	/** Replace the handlers the next frames reach; nothing reopens. */
	public setHandlers(handlers: StreamHandlersLike<E>): void {
		this.handlers = handlers;
	}

	public readonly setInput = (input: I | null): void => {
		const key = input === null ? null : stableKey(input);
		if (key === this.key) {
			return;
		}
		this.cancel?.();
		this.cancel = null;
		this.key = key;
		if (input === null || key === null) {
			this.publish(IDLE_STREAM);
			return;
		}
		this.cancel = this.start(input);
	};

	public readonly close = (): void => {
		this.setInput(null);
	};

	private start(input: I): () => void {
		let cancelled = false;
		let handle: StreamHandleLike | null = null;
		const update = (change: (previous: StreamState<E>) => StreamState<E>) => {
			if (!cancelled) {
				this.publish(change(this.getSnapshot()));
			}
		};
		this.publish({
			status: "opening",
			lastEvent: null,
			terminal: null,
			error: null,
		});
		this.open(input, {
			onEvent: (event) => {
				if (cancelled) {
					return;
				}
				this.handlers.onEvent?.(event);
				update((previous) => ({ ...previous, lastEvent: event }));
			},
			onTerminal: (terminal) => {
				if (cancelled) {
					return;
				}
				this.handlers.onTerminal?.(terminal);
				update((previous) => ({ ...previous, status: "ended", terminal }));
			},
		}).then(
			(opened) => {
				if (cancelled) {
					opened.close();
					return;
				}
				handle = opened;
				update((previous) =>
					previous.status === "ended"
						? previous
						: { ...previous, status: "open" },
				);
			},
			(error: unknown) => {
				update(() => ({
					status: "failed",
					lastEvent: null,
					terminal: null,
					error: asError(error),
				}));
			},
		);
		return () => {
			cancelled = true;
			handle?.close();
		};
	}
}

// ---------------------------------------------------------------------------
// FormStore
// ---------------------------------------------------------------------------

/**
 * The input families a declared request can ask for: the same names the
 * Python `qgis_sdk.ui` catalogue draws, so a form on either side of the
 * bridge renders one declaration the same way.
 */
export type FormFieldKind =
	| "text"
	| "integer"
	| "number"
	| "boolean"
	| "choice"
	| "layer"
	| "crs"
	| "metres"
	| "file"
	| "directory"
	| "field"
	| "range"
	| "colour";

const FIELD_KINDS: ReadonlySet<string> = new Set<FormFieldKind>([
	"text",
	"integer",
	"number",
	"boolean",
	"choice",
	"layer",
	"crs",
	"metres",
	"file",
	"directory",
	"field",
	"range",
	"colour",
]);
const PRIMITIVE_KINDS: Readonly<Record<string, FormFieldKind>> = {
	string: "text",
	integer: "integer",
	number: "number",
	boolean: "boolean",
};
const NUMERIC_KINDS: ReadonlySet<FormFieldKind> = new Set<FormFieldKind>([
	"integer",
	"number",
	"metres",
	"range",
]);
const DETAIL_KEYS = ["minimum", "maximum", "step", "of", "filters", "alpha"];

/** One input of a declared action, as a page should render it. */
export interface FormField {
	readonly name: string;
	/** `buffer_distance` -> `Buffer distance`. */
	readonly label: string;
	readonly kind: FormFieldKind;
	readonly required: boolean;
	readonly nullable: boolean;
	/** The `enum` of a `choice` field; empty otherwise. */
	readonly choices: readonly unknown[];
	/** Bounds, a parent input, picker filters: what the kind needs beyond a name. */
	readonly details: Readonly<Record<string, unknown>>;
	/** The property schema the value is validated against. */
	readonly schema: DeclaredSchema;
}

/** Render a field name as a label. */
export function labelFor(name: string): string {
	const spaced = name.replace(/_/g, " ").trim();
	return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

function concrete(schema: DeclaredSchema): [DeclaredSchema, boolean] {
	const branches = schema.anyOf;
	if (!Array.isArray(branches)) {
		return [schema, false];
	}
	const nonNull = branches.filter(
		(branch): branch is DeclaredSchema =>
			isPlainRecord(branch) && branch.type !== "null",
	);
	if (nonNull.length === 1 && nonNull.length !== branches.length) {
		return [nonNull[0] as DeclaredSchema, true];
	}
	throw new QgisSdkStoreError(
		"a union field must be one type or that type plus null to be rendered",
	);
}

function kindFor(
	owner: string,
	name: string,
	schema: DeclaredSchema,
): FormFieldKind {
	const intent = schema["x-qgis-sdk"];
	const marked = isPlainRecord(intent) ? intent.kind : undefined;
	if (typeof marked === "string") {
		if (!FIELD_KINDS.has(marked)) {
			throw new QgisSdkStoreError(
				`${owner}: field ${name} has unknown kind ${JSON.stringify(marked)}`,
			);
		}
		return marked as FormFieldKind;
	}
	if ("enum" in schema) {
		return "choice";
	}
	const kind = PRIMITIVE_KINDS[String(schema.type)];
	if (kind === undefined) {
		throw new QgisSdkStoreError(
			`${owner}: field ${name} has no input for its schema; declare a primitive, an enum or a kind`,
		);
	}
	return kind;
}

/**
 * The fields of a declared request schema, in declaration order: the
 * TypeScript twin of `qgis_sdk.ui.schema_fields`.
 */
export function schemaFields(
	schema: DeclaredSchema,
	owner = "form",
): readonly FormField[] {
	const properties = schema.properties;
	if (!isPlainRecord(properties)) {
		return Object.freeze([]);
	}
	const required = new Set(
		Array.isArray(schema.required) ? (schema.required as string[]) : [],
	);
	return Object.freeze(
		Object.entries(properties).map(([name, property]) => {
			if (!isPlainRecord(property)) {
				throw new QgisSdkStoreError(`${owner}: field ${name} is not a schema`);
			}
			const [shape, nullable] = concrete(property);
			const kind = kindFor(owner, name, shape);
			const intent = isPlainRecord(shape["x-qgis-sdk"])
				? shape["x-qgis-sdk"]
				: {};
			const merged: Record<string, unknown> = { ...shape, ...intent };
			const details =
				kind === "integer"
					? {}
					: Object.fromEntries(
							DETAIL_KEYS.filter((key) => key in merged).map((key) => [
								key,
								merged[key],
							]),
						);
			return Object.freeze({
				name,
				label: labelFor(name),
				kind,
				required: required.has(name) && !nullable,
				nullable,
				choices: Object.freeze(
					kind === "choice" && Array.isArray(shape.enum) ? [...shape.enum] : [],
				),
				details: Object.freeze(details),
				schema: property,
			});
		}),
	);
}

/** The values a form holds: one entry per field the user or the schema set. */
export type FormValues = Readonly<Record<string, unknown>>;

/** Where one form stands. */
export interface FormState<R> {
	readonly values: FormValues;
	/** Every issue the current values have against the request schema. */
	readonly issues: readonly QgisSdkValidationIssue[];
	/** The first issue code per field name, for a label to show. */
	readonly errors: Readonly<Record<string, string>>;
	readonly valid: boolean;
	/** A value changed since construction or the last `reset`. */
	readonly dirty: boolean;
	/** `submit` was attempted since construction or the last `reset`. */
	readonly submitted: boolean;
	/** The latest submission, as an operation store reports it. */
	readonly submission: OperationState<R>;
}

/** Options for {@link FormStore}. */
export interface FormOptions {
	/** Values to start from; the declared dialect has no defaults of its own. */
	readonly initial?: FormValues;
}

type RequestOf<O, K extends keyof O> = O[K] extends OperationShape
	? O[K]["request"]
	: never;
type ResultOf<O, K extends keyof O> = O[K] extends OperationShape
	? O[K]["result"]
	: never;

/**
 * Walk `qgis` by the dotted id to the method a declared action became.
 */
function operationOf<I, R>(
	qgis: QgisSdkCore<unknown, unknown>,
	id: string,
): Operation<I, R> {
	let node: unknown = qgis;
	for (const segment of id.split(".")) {
		node =
			isPlainRecord(node) || typeof node === "function"
				? (node as Record<string, unknown>)[segment]
				: undefined;
	}
	if (typeof node !== "function") {
		throw new QgisSdkStoreError(`${id} is not an operation of this QgisSdk`);
	}
	return node as Operation<I, R>;
}

function coerce(field: FormField, value: unknown): unknown {
	if (value === "" && field.kind !== "text") {
		return undefined;
	}
	if (NUMERIC_KINDS.has(field.kind) && typeof value === "string") {
		const trimmed = value.trim();
		if (
			trimmed !== "" &&
			/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(trimmed)
		) {
			const number = Number(trimmed);
			if (field.kind !== "integer" || Number.isInteger(number)) {
				return number;
			}
		}
	}
	return value;
}

/**
 * Bind the request of one declared action to its schema.
 *
 * The fields come from the declaration, so a page renders `form.fields`
 * instead of guessing; `set` coerces what an `<input>` yields (`"3"` for a
 * numeric field, `""` for an unset one) and re-validates; `submit` refuses
 * invalid values without a call and otherwise runs the operation through an
 * {@link OperationStore}, whose state is `submission`.
 */
export class FormStore<Req extends object, R> extends BaseStore<FormState<R>> {
	public readonly id: string;
	public readonly title: string;
	public readonly fields: readonly FormField[];
	private readonly byName: ReadonlyMap<string, FormField>;
	private readonly request: DeclaredSchema;
	private readonly initial: FormValues;
	private readonly operation: OperationStore<Req, R>;
	private readonly unsubscribe: () => void;

	public constructor(
		qgis: QgisSdkCore<unknown, unknown>,
		id: string,
		options: FormOptions = {},
	) {
		const action = qgis.schema.actions.find((candidate) => candidate.id === id);
		if (action === undefined) {
			throw new QgisSdkStoreError(
				`${id} is not a declared action of this schema`,
			);
		}
		const fields = schemaFields(action.request, `form ${id}`);
		const initial = FormStore.defaults(options.initial ?? {});
		super(FormStore.evaluate(initial, action.request, false, false, IDLE));
		this.id = id;
		this.title = action.title;
		this.fields = fields;
		this.byName = new Map(fields.map((field) => [field.name, field]));
		this.request = action.request;
		this.initial = initial;
		this.operation = new OperationStore(operationOf<Req, R>(qgis, id));
		let first = true;
		this.unsubscribe = this.operation.subscribe((submission) => {
			if (first) {
				first = false;
				return;
			}
			const current = this.getSnapshot();
			this.publish({ ...current, submission });
		});
	}

	/** The declaration the form was built from, for a page that renders more. */
	public static describe(
		qgis: QgisSdkCore<unknown, unknown>,
		id: string,
	): ActionDescription | undefined {
		return qgis.schema.actions.find((candidate) => candidate.id === id);
	}

	private static defaults(initial: FormValues): FormValues {
		// The declared dialect carries no `default` keyword: what a form starts
		// from is the page's choice, and an unset required field is an issue
		// the page shows once `submitted` is true.
		return Object.freeze(
			Object.fromEntries(
				Object.entries(initial).filter(([, value]) => value !== undefined),
			),
		);
	}

	private static evaluate<R>(
		values: FormValues,
		request: DeclaredSchema,
		dirty: boolean,
		submitted: boolean,
		submission: OperationState<R>,
	): FormState<R> {
		const issues = validateAgainstSchema(values, request);
		const errors: Record<string, string> = {};
		for (const issue of issues) {
			const [head] = issue.path;
			const name = typeof head === "string" ? head : "";
			if (!(name in errors)) {
				errors[name] = issue.code;
			}
		}
		return Object.freeze({
			values,
			issues: Object.freeze(issues),
			errors: Object.freeze(errors),
			valid: issues.length === 0,
			dirty,
			submitted,
			submission,
		});
	}

	/** Set one field; `undefined` unsets it. */
	public readonly set = (name: string, value: unknown): void => {
		this.setValues({ [name]: value });
	};

	/** Set several fields at once. */
	public readonly setValues = (changes: FormValues): void => {
		const current = this.getSnapshot();
		const values: Record<string, unknown> = { ...current.values };
		for (const [name, raw] of Object.entries(changes)) {
			const field = this.byName.get(name);
			if (field === undefined) {
				throw new QgisSdkStoreError(`${this.id} has no field ${name}`);
			}
			const value = coerce(field, raw);
			if (value === undefined) {
				delete values[name];
			} else {
				values[name] = value;
			}
		}
		this.publish(
			FormStore.evaluate(
				Object.freeze(values),
				this.request,
				true,
				current.submitted,
				current.submission,
			),
		);
	};

	/** The declared field, for a renderer working from a name. */
	public field(name: string): FormField {
		const field = this.byName.get(name);
		if (field === undefined) {
			throw new QgisSdkStoreError(`${this.id} has no field ${name}`);
		}
		return field;
	}

	/** Back to the initial values and an idle submission; aborts a call in flight. */
	public readonly reset = (): void => {
		this.operation.reset();
		this.publish(
			FormStore.evaluate(this.initial, this.request, false, false, IDLE),
		);
	};

	/** Abort a submission in flight; the values stay. */
	public readonly abort = (): void => {
		this.operation.abort();
	};

	/**
	 * Validate, then run the action with the current values. Resolves with the
	 * result, or `undefined` when the values are invalid (no call is made) or
	 * the call failed, was aborted or superseded - `submission` says which.
	 */
	public readonly submit = async (): Promise<R | undefined> => {
		const current = this.getSnapshot();
		if (!current.valid) {
			this.publish({ ...current, submitted: true });
			return undefined;
		}
		if (!current.submitted) {
			this.publish({ ...current, submitted: true });
		}
		return this.operation.run(current.values as Req);
	};

	/** Stop following the submission; for an adapter tearing the form down. */
	public dispose(): void {
		this.operation.abort();
		this.unsubscribe();
	}
}

/**
 * The form for `qgis.<id>`, typed from the schema: the request names the
 * fields, the result types the submission.
 */
export function formStore<O, K extends keyof O & string>(
	qgis: QgisSdkCore<O, unknown>,
	id: K,
	options?: FormOptions,
): FormStore<RequestOf<O, K> & object, ResultOf<O, K>> {
	return new FormStore(qgis as QgisSdkCore<unknown, unknown>, id, options);
}

// ---------------------------------------------------------------------------
// HostQueryStore
// ---------------------------------------------------------------------------

/** Where one host query stands. */
export type HostQueryState<T> =
	| { readonly status: "idle" }
	| { readonly status: "loading" }
	| { readonly status: "ok"; readonly value: T }
	| { readonly status: "error"; readonly error: Error }
	| {
			/** The handshake did not grant `operation`; no call was made. */
			readonly status: "refused";
			readonly operation: HostOperationId;
			readonly message: string;
	  };

const IDLE_QUERY: HostQueryState<never> = Object.freeze({ status: "idle" });

/** What a host query runs once the grant is confirmed. */
export type HostQueryLoader<T> = (
	host: QgisSdkHost,
	options: { readonly signal: AbortSignal },
) => Promise<T>;

/**
 * Read the curated host surface, grant first.
 *
 * `refresh` waits for the handshake, then - when `qgis.host.granted` lacks
 * the operation the query needs - settles on `refused` without a call, so a
 * page can show "ask the plugin author for `layers.read`" instead of a
 * `not_authorized` fault. Otherwise the loader runs with latest-wins
 * semantics like an operation store.
 */
export class HostQueryStore<T> extends BaseStore<HostQueryState<T>> {
	private generation = 0;
	private controller: AbortController | null = null;

	public constructor(
		private readonly qgis: QgisSdkCore<unknown, unknown>,
		public readonly operation: HostOperationId,
		private readonly loader: HostQueryLoader<T>,
	) {
		super(IDLE_QUERY);
	}

	public readonly abort = (): void => {
		this.generation += 1;
		this.controller?.abort();
		this.controller = null;
	};

	public readonly reset = (): void => {
		this.abort();
		this.publish(IDLE_QUERY);
	};

	public readonly refresh = async (): Promise<T | undefined> => {
		this.abort();
		const mine = this.generation;
		const controller = new AbortController();
		this.controller = controller;
		this.publish({ status: "loading" });
		try {
			await this.qgis.ready;
			if (this.generation !== mine) {
				return undefined;
			}
			if (!this.qgis.host.granted.includes(this.operation)) {
				this.publish({
					status: "refused",
					operation: this.operation,
					message: `this view was not granted ${this.operation}`,
				});
				return undefined;
			}
			const value = await this.loader(this.qgis.host, {
				signal: controller.signal,
			});
			if (this.generation !== mine) {
				return undefined;
			}
			this.publish({ status: "ok", value });
			return value;
		} catch (error) {
			if (
				this.generation !== mine ||
				error instanceof QgisSdkBridgeAbortedError
			) {
				return undefined;
			}
			this.publish({ status: "error", error: asError(error) });
			return undefined;
		} finally {
			if (this.controller === controller) {
				this.controller = null;
			}
		}
	};
}

/** Options for {@link layersQuery}. */
export interface LayersQueryOptions {
	/** Items per page while following `next_cursor`; the host's default otherwise. */
	readonly pageSize?: number;
}

/**
 * Every vector layer of the project, following `layers.list` pages to the
 * end: what a layer picker binds to. Needs the `layers.read` grant.
 */
export function layersQuery(
	qgis: QgisSdkCore<unknown, unknown>,
	options: LayersQueryOptions = {},
): HostQueryStore<readonly VectorLayerInfo[]> {
	return new HostQueryStore(qgis, "layers.list", async (host, { signal }) => {
		const items: VectorLayerInfo[] = [];
		let cursor: string | undefined;
		do {
			const page: LayerPage = await host.layers.list(
				{
					...(cursor === undefined ? {} : { cursor }),
					...(options.pageSize === undefined
						? {}
						: { limit: options.pageSize }),
				},
				{ signal },
			);
			items.push(...page.items);
			cursor = page.next_cursor;
		} while (cursor !== undefined);
		return Object.freeze(items);
	});
}

/**
 * The field names of one vector layer, for a `field` input whose `of` names
 * a layer input: `layers.get` under the `layers.read` grant. A layer's CRS is
 * on the same reply; a project CRS query is not on the wire yet.
 */
export function layerFieldsQuery(
	qgis: QgisSdkCore<unknown, unknown>,
	layerId: string,
): HostQueryStore<readonly string[]> {
	return new HostQueryStore(qgis, "layers.get", async (host, { signal }) => {
		const layer = await host.layers.get({ layer_id: layerId }, { signal });
		return Object.freeze([...layer.field_names]);
	});
}
