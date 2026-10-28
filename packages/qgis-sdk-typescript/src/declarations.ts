/**
 * The version 1 plugin-description contract and its wire limits.
 *
 * Mirrors the QGIS-free `qgis_sdk.models` and `qgis_sdk.declarations`
 * (`schema_version = 1`) contracts without importing browser or Qt globals.
 * `parsePluginDescription` is the browser-side reader of what
 * `describe(app).to_json()` emits; `qgis-sdk bridge generate` is the
 * build-time one.
 */

import { QgisSdkError } from "./errors";
import { isPlainRecord, STREAM_EVENT_KINDS } from "./internal";

export const MAX_SAFE_INTEGER: number = 9_007_199_254_740_991;
export const MIN_SAFE_INTEGER: number = -9_007_199_254_740_991;
export const PLUGIN_DESCRIPTION_SCHEMA_VERSION: 1 = 1;

export type ValidationDirection = "request" | "result";

export interface SerializedValidationIssue {
	readonly path: (string | number)[];
	readonly code: string;
}

export interface SerializedContractValidationError {
	readonly code: string;
	readonly direction: ValidationDirection;
	readonly issues: SerializedValidationIssue[];
}

export interface ActionDescription {
	readonly id: string;
	readonly title: string;
	readonly handler: string;
	readonly request: Readonly<Record<string, unknown>>;
	readonly result: Readonly<Record<string, unknown>>;
}

/** The event kinds a stream may declare; the frame carries the same three. */
export type StreamEventKind = "data" | "progress" | "state";

/**
 * A declared stream (decision-28): a request in, one payload schema per
 * declared event kind out. There is no `result`: the reply to a subscription is
 * the protocol's acknowledgement, not something an author declares.
 */
export interface StreamDescription {
	readonly id: string;
	readonly title: string;
	readonly handler: string;
	readonly request: Readonly<Record<string, unknown>>;
	readonly events: Readonly<
		Partial<Record<StreamEventKind, Readonly<Record<string, unknown>>>>
	>;
}

export interface PluginDescription {
	readonly schema_version: 1;
	readonly id: string;
	readonly title: string;
	readonly actions: readonly ActionDescription[];
	/** Declared streams; a description from a host that predates them is empty. */
	readonly streams: readonly StreamDescription[];
}

/**
 * Return whether `value` is a finite integer within the JavaScript-safe wire range.
 */
export function isSafeJsonInteger(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value);
}

/**
 * A declaration cannot be represented or parsed in the versioned contract.
 */
export class QgisSdkDeclarationError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "invalid_declaration");
	}
}

/**
 * Safe, structured location and category for a rejected contract value.
 */
export class QgisSdkValidationIssue {
	public readonly path: readonly (string | number)[];
	public readonly code: string;

	public constructor(path: readonly (string | number)[], code: string) {
		this.path = Object.freeze([...path]);
		this.code = code;
	}

	public toJSON(): SerializedValidationIssue {
		return {
			path: [...this.path],
			code: this.code,
		};
	}
}

/**
 * A request or result did not satisfy its declared wire contract.
 */
export class QgisSdkContractValidationError extends QgisSdkError {
	public readonly direction: ValidationDirection;
	public readonly issues: readonly QgisSdkValidationIssue[];

	public constructor(
		direction: ValidationDirection,
		issues: readonly QgisSdkValidationIssue[],
	) {
		const prefix = direction === "request" ? "Request" : "Result";
		super(`${prefix} contract validation failed`, "contract_validation_failed");
		this.direction = direction;
		this.issues = Object.freeze([...issues]);
	}

	public toJSON(): SerializedContractValidationError {
		return {
			code: this.code,
			direction: this.direction,
			issues: this.issues.map((issue) => issue.toJSON()),
		};
	}
}

const DECLARATION_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_.-]*$/;
const PYTHON_IDENTIFIER_PATTERN = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

function validateDeclarationId(value: unknown, label: string): string {
	if (typeof value !== "string" || !DECLARATION_ID_PATTERN.test(value)) {
		throw new QgisSdkDeclarationError(
			`Invalid ${label} id: expected [a-zA-Z][a-zA-Z0-9_.-]*`,
		);
	}
	return value;
}

function validateNonBlankTitle(value: unknown, id: string): string {
	if (typeof value !== "string" || value.trim().length === 0) {
		throw new QgisSdkDeclarationError(`${id}: title must be a nonempty string`);
	}
	return value;
}

function parseOperationHead(
	raw: unknown,
	label: string,
): {
	readonly raw: Record<string, unknown>;
	readonly id: string;
	readonly title: string;
	readonly handler: string;
	readonly request: Readonly<Record<string, unknown>>;
} {
	if (!isPlainRecord(raw)) {
		throw new QgisSdkDeclarationError(
			`${label[0]?.toUpperCase()}${label.slice(1)} description must be an object`,
		);
	}
	const id = validateDeclarationId(raw.id, label);
	const title = validateNonBlankTitle(raw.title, id);
	if (
		typeof raw.handler !== "string" ||
		!PYTHON_IDENTIFIER_PATTERN.test(raw.handler)
	) {
		throw new QgisSdkDeclarationError(
			`${id}: handler must be a valid Python identifier`,
		);
	}
	if (!isPlainRecord(raw.request)) {
		throw new QgisSdkDeclarationError(
			`${id}: request schema must be an object`,
		);
	}
	return {
		raw,
		id,
		title,
		handler: raw.handler,
		request: Object.freeze({ ...raw.request }),
	};
}

function parseActionDescription(raw: unknown): ActionDescription {
	const head = parseOperationHead(raw, "action");
	if (!isPlainRecord(head.raw.result)) {
		throw new QgisSdkDeclarationError(
			`${head.id}: result schema must be an object`,
		);
	}
	return Object.freeze({
		id: head.id,
		title: head.title,
		handler: head.handler,
		request: head.request,
		result: Object.freeze({ ...head.raw.result }),
	});
}

function parseStreamDescription(raw: unknown): StreamDescription {
	const head = parseOperationHead(raw, "stream");
	const declared = head.raw.events;
	if (!isPlainRecord(declared) || Object.keys(declared).length === 0) {
		throw new QgisSdkDeclarationError(
			`${head.id}: events must map at least one event kind to a schema`,
		);
	}
	const events: Partial<
		Record<StreamEventKind, Readonly<Record<string, unknown>>>
	> = {};
	for (const [kind, schema] of Object.entries(declared)) {
		if (!STREAM_EVENT_KINDS.includes(kind as StreamEventKind)) {
			throw new QgisSdkDeclarationError(
				`${head.id}: ${kind} is not a stream event kind`,
			);
		}
		if (!isPlainRecord(schema)) {
			throw new QgisSdkDeclarationError(
				`${head.id}: events.${kind} schema must be an object`,
			);
		}
		events[kind as StreamEventKind] = Object.freeze({ ...schema });
	}
	return Object.freeze({
		id: head.id,
		title: head.title,
		handler: head.handler,
		request: head.request,
		events: Object.freeze(events),
	});
}

/**
 * Parse and validate a version 1 `PluginDescription` emitted by `describe(app)`.
 */
export function parsePluginDescription(
	input: string | Readonly<Record<string, unknown>>,
): PluginDescription {
	let parsed: unknown = input;
	if (typeof input === "string") {
		try {
			parsed = JSON.parse(input);
		} catch {
			throw new QgisSdkDeclarationError("Plugin description is not valid JSON");
		}
	}
	if (!isPlainRecord(parsed)) {
		throw new QgisSdkDeclarationError("Plugin description must be an object");
	}
	if (parsed.schema_version !== PLUGIN_DESCRIPTION_SCHEMA_VERSION) {
		throw new QgisSdkDeclarationError(
			`Unsupported plugin description schema_version: ${String(parsed.schema_version)}`,
		);
	}
	const id = validateDeclarationId(parsed.id, "plugin");
	const title = validateNonBlankTitle(parsed.title, id);
	if (!Array.isArray(parsed.actions)) {
		throw new QgisSdkDeclarationError(`${id}: actions must be an array`);
	}
	const declaredStreams = parsed.streams ?? [];
	if (!Array.isArray(declaredStreams)) {
		throw new QgisSdkDeclarationError(`${id}: streams must be an array`);
	}
	// Actions and streams share one id namespace (decision-28).
	const seenIds = new Set<string>();
	const claim = (operationId: string, label: string): void => {
		if (seenIds.has(operationId)) {
			throw new QgisSdkDeclarationError(
				`${id}: duplicate ${label} id ${operationId}`,
			);
		}
		seenIds.add(operationId);
	};
	const actions: ActionDescription[] = [];
	for (const item of parsed.actions) {
		const action = parseActionDescription(item);
		claim(action.id, "action");
		actions.push(action);
	}
	const streams: StreamDescription[] = [];
	for (const item of declaredStreams) {
		const stream = parseStreamDescription(item);
		claim(stream.id, "stream");
		streams.push(stream);
	}
	const byId = (
		left: { readonly id: string },
		right: { readonly id: string },
	): number => (left.id < right.id ? -1 : 1);
	actions.sort(byId);
	streams.sort(byId);
	return Object.freeze({
		schema_version: PLUGIN_DESCRIPTION_SCHEMA_VERSION,
		id,
		title,
		actions: Object.freeze(actions),
		streams: Object.freeze(streams),
	});
}
