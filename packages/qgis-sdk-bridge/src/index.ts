/**
 * Public 0.1.0 contract, wire-limit, and error primitives for the QGIS SDK bridge.
 *
 * Mirrors the QGIS-free `qgis_sdk.models` and `qgis_sdk.declarations`
 * (`schema_version = 1`) contracts without importing browser or Qt globals.
 */

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

export interface PluginDescription {
	readonly schema_version: 1;
	readonly id: string;
	readonly title: string;
	readonly actions: readonly ActionDescription[];
}

/**
 * Return whether `value` is a finite integer within the JavaScript-safe wire range.
 */
export function isSafeJsonInteger(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value);
}

/**
 * Base class for expected SDK errors across the bridge boundary.
 */
export class QgisSdkError extends Error {
	public readonly code: string;

	public constructor(message: string, code: string = "sdk_error") {
		super(message);
		this.name = new.target.name;
		this.code = code;
	}
}

/**
 * An operation attempted to use an already disposed owner scope.
 */
export class QgisSdkScopeClosedError extends QgisSdkError {
	public constructor() {
		super("This resource scope has been disposed", "scope_closed");
	}
}

/**
 * The selected runtime does not offer an explicitly requested capability.
 */
export class QgisSdkUnsupportedCapabilityError extends QgisSdkError {
	public readonly capability: string;

	public constructor(capability: string) {
		super(
			`Capability ${JSON.stringify(capability)} is unavailable in this runtime`,
			"unsupported_capability",
		);
		this.capability = capability;
	}
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

function isPlainRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

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

function parseActionDescription(raw: unknown): ActionDescription {
	if (!isPlainRecord(raw)) {
		throw new QgisSdkDeclarationError("Action description must be an object");
	}
	const id = validateDeclarationId(raw.id, "action");
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
	if (!isPlainRecord(raw.result)) {
		throw new QgisSdkDeclarationError(`${id}: result schema must be an object`);
	}
	return Object.freeze({
		id,
		title,
		handler: raw.handler,
		request: Object.freeze({ ...raw.request }),
		result: Object.freeze({ ...raw.result }),
	});
}

/**
 * Parse and validate a version 1 `PluginDescription` emitted by `describe_plugin`.
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
	const seenIds = new Set<string>();
	const actions: ActionDescription[] = [];
	for (const item of parsed.actions) {
		const action = parseActionDescription(item);
		if (seenIds.has(action.id)) {
			throw new QgisSdkDeclarationError(
				`${id}: duplicate action id ${action.id}`,
			);
		}
		seenIds.add(action.id);
		actions.push(action);
	}
	actions.sort((left, right) => (left.id < right.id ? -1 : 1));
	return Object.freeze({
		schema_version: PLUGIN_DESCRIPTION_SCHEMA_VERSION,
		id,
		title,
		actions: Object.freeze(actions),
	});
}
