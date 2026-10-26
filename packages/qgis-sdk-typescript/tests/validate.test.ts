/**
 * The page-side validator mirrors `qgis_sdk.bridge.schema` (TASK-66 AC #2):
 * the same dialect, the same asymmetry, and a declaration fault is thrown
 * rather than reported as an issue in the value.
 *
 * The schemas here are what `describe_plugin` emits for the Python types the
 * acceptance criterion names: primitives, `list`/`tuple`, `X | None`,
 * `Literal`, and a nested dataclass.
 */

import { expect, test } from "@archont561/bun-test-utils";
import { MAX_SAFE_INTEGER, QgisSdkDeclarationError } from "../src/declarations";
import { QgisSdkContractError, validateAgainstSchema } from "../src/validate";

const INTEGER = {
	type: "integer",
	minimum: -MAX_SAFE_INTEGER,
	maximum: MAX_SAFE_INTEGER,
} as const;

function codes(
	value: unknown,
	schema: Readonly<Record<string, unknown>>,
	allowUnknown = false,
): string[] {
	return validateAgainstSchema(value, schema, { allowUnknown }).map(
		(issue) => `${issue.path.join(".")}:${issue.code}`,
	);
}

test("the five primitives accept their JSON type and nothing else", () => {
	expect(codes("x", { type: "string" })).toEqual([]);
	expect(codes(1, { type: "string" })).toEqual([":type"]);
	expect(codes(true, { type: "boolean" })).toEqual([]);
	expect(codes(1, { type: "boolean" })).toEqual([":type"]);
	expect(codes(null, { type: "null" })).toEqual([]);
	expect(codes(undefined, { type: "null" })).toEqual([":type"]);
	expect(codes(1.5, { type: "number" })).toEqual([]);
	expect(codes(2, { type: "number" })).toEqual([]);
	expect(codes("2", { type: "number" })).toEqual([":type"]);
	expect(codes(Number.NaN, { type: "number" })).toEqual([":not_finite"]);
	expect(codes(Number.POSITIVE_INFINITY, { type: "number" })).toEqual([
		":not_finite",
	]);
});

test("an integer is a whole, safe number; a boolean is never one", () => {
	expect(codes(7, INTEGER)).toEqual([]);
	expect(codes(2.0, INTEGER)).toEqual([]);
	expect(codes(1.5, INTEGER)).toEqual([":type"]);
	expect(codes(true, INTEGER)).toEqual([":type"]);
	expect(codes(MAX_SAFE_INTEGER + 2, INTEGER)).toEqual([":maximum"]);
	expect(codes(-MAX_SAFE_INTEGER - 2, INTEGER)).toEqual([":minimum"]);
	expect(codes(11, { type: "integer", maximum: 10 })).toEqual([":maximum"]);
	expect(codes(0, { type: "number", minimum: 1 })).toEqual([":minimum"]);
});

test("a string pattern matches the whole value, as re.fullmatch does", () => {
	const schema = { type: "string", pattern: "[a-z]+" };
	expect(codes("abc", schema)).toEqual([]);
	expect(codes("abc1", schema)).toEqual([":pattern"]);
	expect(codes("1abc", schema)).toEqual([":pattern"]);
	expect(() => codes("x", { type: "string", pattern: "(" })).toThrow(
		QgisSdkDeclarationError,
	);
});

test("list and tuple are arrays whose items are each checked by index", () => {
	const names = { type: "array", items: { type: "string" } };
	expect(codes(["a", "b"], names)).toEqual([]);
	expect(codes([], names)).toEqual([]);
	expect(codes(["a", 1, null], names)).toEqual(["1:type", "2:type"]);
	expect(codes("a", names)).toEqual([":type"]);
	const nested = { type: "array", items: { type: "array", items: INTEGER } };
	expect(codes([[1], [2, 3]], nested)).toEqual([]);
	expect(codes([[1], ["2"]], nested)).toEqual(["1.0:type"]);
	expect(codes([1, "x"], { type: "array" })).toEqual([]);
});

test("`X | None` is an anyOf: one branch has to match", () => {
	const optional = { anyOf: [{ type: "string" }, { type: "null" }] };
	expect(codes("label", optional)).toEqual([]);
	expect(codes(null, optional)).toEqual([]);
	expect(codes(1, optional)).toEqual([":any_of"]);
	expect(() => codes(1, { anyOf: [] })).toThrow(QgisSdkDeclarationError);
});

test("a Literal is an enum compared by JSON equality", () => {
	const mode = { enum: ["fast", "exact", 1, true, null] };
	expect(codes("fast", mode)).toEqual([]);
	expect(codes(1, mode)).toEqual([]);
	expect(codes(true, mode)).toEqual([]);
	expect(codes(null, mode)).toEqual([]);
	expect(codes("slow", mode)).toEqual([":enum"]);
	// `true` is not `1`, and `1.0` is `1`.
	expect(codes(1, { enum: [true] })).toEqual([":enum"]);
	expect(codes(1.0, { enum: [1] })).toEqual([]);
	expect(codes({ a: [1] }, { enum: [{ a: [1] }] })).toEqual([]);
	expect(codes({ a: [1] }, { enum: [{ a: [2] }] })).toEqual([":enum"]);
	expect(() => codes(1, { enum: "fast" })).toThrow(QgisSdkDeclarationError);
});

const DETAILS = {
	type: "object",
	properties: {
		layer_id: { type: "string" },
		options: {
			type: "object",
			properties: {
				include_fields: { type: "boolean" },
				limit: INTEGER,
			},
			additionalProperties: false,
		},
	},
	additionalProperties: false,
	required: ["layer_id", "options"],
} as const;

test("a nested dataclass is an object inside an object, checked by path", () => {
	expect(codes({ layer_id: "sites", options: {} }, DETAILS)).toEqual([]);
	expect(
		codes(
			{ layer_id: "sites", options: { include_fields: true, limit: 5 } },
			DETAILS,
		),
	).toEqual([]);
	expect(codes({ options: {} }, DETAILS)).toEqual(["layer_id:required"]);
	expect(codes({ layer_id: "sites", options: null }, DETAILS)).toEqual([
		"options:type",
	]);
	expect(
		codes({ layer_id: "sites", options: { limit: "5" } }, DETAILS),
	).toEqual(["options.limit:type"]);
	expect(codes([], DETAILS)).toEqual([":type"]);
	expect(codes("sites", DETAILS)).toEqual([":type"]);
});

test("a request is strict and a result lenient about unknown properties", () => {
	const value = { layer_id: "sites", options: { limit: 1, extra: 1 }, more: 2 };
	expect(codes(value, DETAILS)).toEqual([
		"options.extra:unknown_property",
		"more:unknown_property",
	]);
	expect(codes(value, DETAILS, true)).toEqual([]);
	// A required field is still required when unknown ones are allowed.
	expect(codes({ options: {}, more: 2 }, DETAILS, true)).toEqual([
		"layer_id:required",
	]);
	// An open object (no `additionalProperties: false`) never refuses a key.
	const open = { type: "object", properties: { a: { type: "string" } } };
	expect(codes({ a: "x", b: 1 }, open)).toEqual([]);
});

test("a prefix path lands in front of every issue", () => {
	const issues = validateAgainstSchema(
		{ limit: "x" },
		DETAILS.properties.options,
		{
			path: ["payload"],
		},
	);
	expect(issues.map((issue) => issue.path)).toEqual([["payload", "limit"]]);
});

test("a schema outside the declared dialect is a declaration fault, not an issue", () => {
	expect(() => codes(1, { type: "date" })).toThrow(QgisSdkDeclarationError);
	expect(() => codes(1, { oneOf: [] })).toThrow(QgisSdkDeclarationError);
	expect(() => codes(1, {})).toThrow(QgisSdkDeclarationError);
	expect(() => codes({}, { type: "object", properties: [] })).toThrow(
		QgisSdkDeclarationError,
	);
	expect(() => codes({}, { type: "object", required: "a" })).toThrow(
		QgisSdkDeclarationError,
	);
	// `title` and `description` are documentation, not constraints.
	expect(codes("x", { type: "string", title: "T", description: "D" })).toEqual(
		[],
	);
});

test("a contract error carries the operation, the direction and the issues", () => {
	const issues = validateAgainstSchema({ options: {} }, DETAILS);
	const error = new QgisSdkContractError("sites.details", "request", issues);
	expect(error.code).toBe("contract_validation_failed");
	expect(error.name).toBe("QgisSdkContractError");
	expect(error.operation).toBe("sites.details");
	expect(error.direction).toBe("request");
	expect(error.message).toBe(
		"sites.details: the request does not match the declared contract: layer_id required",
	);
	expect(error.toJSON()).toEqual({
		code: "contract_validation_failed",
		operation: "sites.details",
		direction: "request",
		issues: [{ path: ["layer_id"], code: "required" }],
	});
	expect(Object.isFrozen(error.issues)).toBe(true);
	const bare = new QgisSdkContractError("sites.watch", "event", []);
	expect(bare.message).toBe(
		"sites.watch: the event does not match the declared contract",
	);
});
