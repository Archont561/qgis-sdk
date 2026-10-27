/** {@link FormStore}: one declared action's request bound to its schema. */

import type {
	ActionDescription,
	QgisSdkValidationIssue,
} from "../declarations";
import { isPlainRecord } from "../internal";
import type { QgisSdkCore } from "../qgis-sdk";
import type { OperationShape } from "../schema";
import { type DeclaredSchema, validateAgainstSchema } from "../validate";
import { BaseStore, QgisSdkStoreError } from "./base";
import {
	IDLE,
	type Operation,
	type OperationState,
	OperationStore,
} from "./operation";

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
