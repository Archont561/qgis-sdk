/**
 * Validate a value against the schema subset `describe_plugin` emits.
 *
 * This is the TypeScript side of `qgis_sdk.bridge.schema`: the same closed
 * dialect (objects with `properties`/`required`/`additionalProperties`, arrays
 * with `items`, the five JSON primitives, `anyOf` and `enum`, the integer
 * bounds and `pattern`) checked the same way, so `QgisSdk` refuses on the page
 * exactly what the host would refuse a message later. Anything outside the
 * dialect is a declaration fault and throws; a value that does not fit is an
 * issue the caller reports.
 *
 * The two asymmetries of decision-22 hold here too: a request is checked
 * strictly (an unknown property is an issue when the schema closes the
 * object), a result or an event leniently (`allowUnknown`), so a host may add
 * a field without breaking an older page while a missing or mistyped field is
 * still caught.
 */

import {
	QgisSdkDeclarationError,
	QgisSdkValidationIssue,
	type SerializedValidationIssue,
} from "./declarations";
import { QgisSdkError } from "./errors";
import { isPlainRecord } from "./internal";

/** One schema of the declared dialect, as the description carries it. */
export type DeclaredSchema = Readonly<Record<string, unknown>>;

/** Options for {@link validateAgainstSchema}. */
export interface ValidateOptions {
	/** Ignore properties the schema does not name (results and events). */
	readonly allowUnknown?: boolean;
	/** Where the value sits, prefixed to every issue's path. */
	readonly path?: readonly (string | number)[];
}

/** Which side of a call a contract issue belongs to. */
export type ContractDirection = "request" | "result" | "event";

/** The JSON form of {@link QgisSdkContractError}. */
export interface SerializedContractError {
	readonly code: string;
	readonly operation: string;
	readonly direction: ContractDirection;
	readonly issues: SerializedValidationIssue[];
}

/**
 * An argument, a reply or an event does not match the declared contract.
 *
 * The code is the one both languages use for this category, so a page that
 * already matches `contract_validation_failed` needs no second branch.
 */
export class QgisSdkContractError extends QgisSdkError {
	public readonly operation: string;
	public readonly direction: ContractDirection;
	public readonly issues: readonly QgisSdkValidationIssue[];

	public constructor(
		operation: string,
		direction: ContractDirection,
		issues: readonly QgisSdkValidationIssue[],
	) {
		const detail = issues[0] === undefined ? "" : `: ${describe(issues[0])}`;
		super(
			`${operation}: the ${direction} does not match the declared contract${detail}`,
			"contract_validation_failed",
		);
		this.operation = operation;
		this.direction = direction;
		this.issues = Object.freeze([...issues]);
	}

	public toJSON(): SerializedContractError {
		return {
			code: this.code,
			operation: this.operation,
			direction: this.direction,
			issues: this.issues.map((issue) => issue.toJSON()),
		};
	}
}

function describe(issue: QgisSdkValidationIssue): string {
	const where = issue.path.length === 0 ? "value" : issue.path.join(".");
	return `${where} ${issue.code}`;
}

const PRIMITIVES: ReadonlySet<string> = new Set([
	"string",
	"boolean",
	"integer",
	"number",
	"null",
	"array",
	"object",
]);

const KNOWN_KEYWORDS: ReadonlySet<string> = new Set([
	"type",
	"properties",
	"required",
	"additionalProperties",
	"items",
	"anyOf",
	"enum",
	"minimum",
	"maximum",
	"pattern",
	"title",
	"description",
	// The input kind a describer annotated (`{ kind: "layer" }`); forms and
	// pages read it, validation reads past it.
	"x-qgis-sdk",
]);

type Path = readonly (string | number)[];

/**
 * Return every issue `value` has against `schema`; an empty array is a match.
 *
 * Throws {@link QgisSdkDeclarationError} when `schema` leaves the declared
 * dialect, because that is a fault in the declaration, never in the value.
 */
export function validateAgainstSchema(
	value: unknown,
	schema: DeclaredSchema,
	options: ValidateOptions = {},
): QgisSdkValidationIssue[] {
	const issues: QgisSdkValidationIssue[] = [];
	check(
		value,
		schema,
		options.path ?? [],
		options.allowUnknown === true,
		issues,
	);
	return issues;
}

function check(
	value: unknown,
	schema: unknown,
	path: Path,
	allowUnknown: boolean,
	issues: QgisSdkValidationIssue[],
): void {
	if (!isPlainRecord(schema)) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: a schema must be an object`,
		);
	}
	const unknown = Object.keys(schema).filter((key) => !KNOWN_KEYWORDS.has(key));
	if (unknown.length > 0) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: unsupported schema keyword(s) ${unknown.sort().join(", ")}`,
		);
	}
	if ("anyOf" in schema) {
		const branches = schema.anyOf;
		if (!Array.isArray(branches) || branches.length === 0) {
			throw new QgisSdkDeclarationError(
				`${where(path)}: anyOf must be a nonempty list`,
			);
		}
		for (const branch of branches) {
			const attempt: QgisSdkValidationIssue[] = [];
			check(value, branch, path, allowUnknown, attempt);
			if (attempt.length === 0) {
				return;
			}
		}
		issues.push(new QgisSdkValidationIssue([...path], "any_of"));
		return;
	}
	if ("enum" in schema) {
		const choices = schema.enum;
		if (!Array.isArray(choices)) {
			throw new QgisSdkDeclarationError(`${where(path)}: enum must be a list`);
		}
		if (!choices.some((choice) => sameJson(choice, value))) {
			issues.push(new QgisSdkValidationIssue([...path], "enum"));
		}
		return;
	}
	const declared = schema.type;
	if (declared === undefined) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: a schema needs a type, anyOf or enum`,
		);
	}
	if (typeof declared !== "string" || !PRIMITIVES.has(declared)) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: unsupported type ${JSON.stringify(declared)}`,
		);
	}
	switch (declared) {
		case "string":
			checkString(value, schema, path, issues);
			return;
		case "boolean":
			if (typeof value !== "boolean") {
				issues.push(new QgisSdkValidationIssue([...path], "type"));
			}
			return;
		case "integer":
			if (typeof value !== "number" || !Number.isInteger(value)) {
				issues.push(new QgisSdkValidationIssue([...path], "type"));
				return;
			}
			checkBounds(value, schema, path, issues);
			return;
		case "number":
			if (typeof value !== "number") {
				issues.push(new QgisSdkValidationIssue([...path], "type"));
				return;
			}
			if (!Number.isFinite(value)) {
				issues.push(new QgisSdkValidationIssue([...path], "not_finite"));
				return;
			}
			checkBounds(value, schema, path, issues);
			return;
		case "null":
			if (value !== null) {
				issues.push(new QgisSdkValidationIssue([...path], "type"));
			}
			return;
		case "array":
			checkArray(value, schema, path, allowUnknown, issues);
			return;
		default:
			checkObject(value, schema, path, allowUnknown, issues);
	}
}

function checkString(
	value: unknown,
	schema: DeclaredSchema,
	path: Path,
	issues: QgisSdkValidationIssue[],
): void {
	if (typeof value !== "string") {
		issues.push(new QgisSdkValidationIssue([...path], "type"));
		return;
	}
	const pattern = schema.pattern;
	if (pattern === undefined || pattern === null) {
		return;
	}
	if (typeof pattern !== "string") {
		throw new QgisSdkDeclarationError(
			`${where(path)}: pattern must be a string`,
		);
	}
	let expression: RegExp;
	try {
		// Python's re.fullmatch: the whole string, with the unicode flag the
		// declaration side already assumes.
		expression = new RegExp(`^(?:${pattern})$`, "u");
	} catch (error) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: pattern ${JSON.stringify(pattern)} is unusable: ${String(error)}`,
		);
	}
	if (!expression.test(value)) {
		issues.push(new QgisSdkValidationIssue([...path], "pattern"));
	}
}

function checkBounds(
	value: number,
	schema: DeclaredSchema,
	path: Path,
	issues: QgisSdkValidationIssue[],
): void {
	const minimum = schema.minimum;
	if (typeof minimum === "number" && value < minimum) {
		issues.push(new QgisSdkValidationIssue([...path], "minimum"));
	}
	const maximum = schema.maximum;
	if (typeof maximum === "number" && value > maximum) {
		issues.push(new QgisSdkValidationIssue([...path], "maximum"));
	}
}

function checkArray(
	value: unknown,
	schema: DeclaredSchema,
	path: Path,
	allowUnknown: boolean,
	issues: QgisSdkValidationIssue[],
): void {
	if (!Array.isArray(value)) {
		issues.push(new QgisSdkValidationIssue([...path], "type"));
		return;
	}
	const items = schema.items;
	if (items === undefined || items === null) {
		return;
	}
	value.forEach((item, index) => {
		check(item, items, [...path, index], allowUnknown, issues);
	});
}

function checkObject(
	value: unknown,
	schema: DeclaredSchema,
	path: Path,
	allowUnknown: boolean,
	issues: QgisSdkValidationIssue[],
): void {
	if (!isPlainRecord(value)) {
		issues.push(new QgisSdkValidationIssue([...path], "type"));
		return;
	}
	const properties = schema.properties ?? {};
	if (!isPlainRecord(properties)) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: properties must be an object`,
		);
	}
	const required = schema.required ?? [];
	if (!Array.isArray(required)) {
		throw new QgisSdkDeclarationError(
			`${where(path)}: required must be a list`,
		);
	}
	for (const key of required) {
		if (typeof key === "string" && !(key in value)) {
			issues.push(new QgisSdkValidationIssue([...path, key], "required"));
		}
	}
	const strict = schema.additionalProperties === false && !allowUnknown;
	for (const [key, item] of Object.entries(value)) {
		if (Object.hasOwn(properties, key)) {
			check(item, properties[key], [...path, key], allowUnknown, issues);
		} else if (strict) {
			issues.push(
				new QgisSdkValidationIssue([...path, key], "unknown_property"),
			);
		}
	}
}

/** JSON equality: `true` is not `1`, and `1` is `1.0`. */
function sameJson(a: unknown, b: unknown): boolean {
	if (a === b) {
		return true;
	}
	if (typeof a !== typeof b || a === null || b === null) {
		return false;
	}
	if (Array.isArray(a)) {
		return (
			Array.isArray(b) &&
			a.length === b.length &&
			a.every((item, index) => sameJson(item, b[index]))
		);
	}
	if (isPlainRecord(a) && isPlainRecord(b)) {
		const keys = Object.keys(a);
		return (
			keys.length === Object.keys(b).length &&
			keys.every((key) => Object.hasOwn(b, key) && sameJson(a[key], b[key]))
		);
	}
	return false;
}

function where(path: Path): string {
	return path.length === 0 ? "value" : path.join(".");
}
