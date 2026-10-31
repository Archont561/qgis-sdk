import { expect, test } from "@archont561/bun-test-utils";
import * as entry from "@";
import {
	BridgeClient,
	isSafeJsonInteger,
	MAX_SAFE_INTEGER,
	MIN_SAFE_INTEGER,
	PLUGIN_DESCRIPTION_SCHEMA_VERSION,
	parsePluginDescription,
	QgisSdkBridgeRemoteError,
	QgisSdkContractValidationError,
	QgisSdkDeclarationError,
	QgisSdkError,
	QgisSdkValidationIssue,
} from "@";
import * as source from "@/src";
import * as bridge from "@/src/bridge";
import * as declarations from "@/src/declarations";
import * as errors from "@/src/errors";
import { isPlainRecord } from "@/src/internal";
import * as processing from "@/src/processing";
import * as qgisSdk from "@/src/qgis-sdk";
import * as schema from "@/src/schema";
import * as stores from "@/src/stores";
import * as validate from "@/src/validate";
import * as webchannel from "@/src/webchannel";

test("the bare @ alias and @/src both resolve the bridge entry point", () => {
	expect(entry).toBe(source);
});

test("all exported exception classes start with the QgisSdk prefix", () => {
	const errorExports = Object.entries(entry as Record<string, unknown>)
		.filter(
			([, value]) =>
				typeof value === "function" && value.prototype instanceof Error,
		)
		.map(([name]) => name);

	expect(errorExports.sort()).toEqual([
		"QgisSdkBridgeAbortedError",
		"QgisSdkBridgeBlobError",
		"QgisSdkBridgeClosedError",
		"QgisSdkBridgeProtocolError",
		"QgisSdkBridgeRemoteError",
		"QgisSdkBridgeTimeoutError",
		"QgisSdkContractError",
		"QgisSdkContractValidationError",
		"QgisSdkDeclarationError",
		"QgisSdkError",
		"QgisSdkStoreError",
		"QgisSdkWebChannelError",
	]);
	for (const name of errorExports) {
		expect(name.startsWith("QgisSdk")).toBe(true);
	}
});

test("the root is the union of the error root, the declarations, the bridge, the SDK, the stores and processing", () => {
	const names = (module: object): string[] => Object.keys(module).sort();
	const expected = new Set([
		...names(errors),
		...names(declarations),
		...names(bridge),
		...names(processing),
		...names(qgisSdk),
		...names(schema),
		...names(stores),
		...names(validate),
		...names(webchannel),
	]);
	expect(names(entry)).toEqual([...expected].sort());
	// One import serves the common page: the client and the error family.
	expect(entry.BridgeClient).toBe(BridgeClient);
	expect(
		new QgisSdkBridgeRemoteError("call-1", { code: "boom", message: "bad" }),
	).toBeInstanceOf(QgisSdkError);
});

test("the root exports no internal helper and no mirror of a Python-only error", () => {
	const names = Object.keys(entry);
	expect(names).not.toContain("isPlainRecord");
	expect(names).not.toContain("STREAM_EVENT_KINDS");
	expect(names).not.toContain("QgisSdkScopeClosedError");
	expect(names).not.toContain("QgisSdkUnsupportedCapabilityError");
});

test("safe integer bounds and predicate match the Python wire contract", () => {
	expect(MAX_SAFE_INTEGER).toBe(9_007_199_254_740_991);
	expect(MIN_SAFE_INTEGER).toBe(-9_007_199_254_740_991);

	expect(isSafeJsonInteger(0)).toBe(true);
	expect(isSafeJsonInteger(2.0)).toBe(true);
	expect(isSafeJsonInteger(MAX_SAFE_INTEGER)).toBe(true);
	expect(isSafeJsonInteger(MIN_SAFE_INTEGER)).toBe(true);

	expect(isSafeJsonInteger(MAX_SAFE_INTEGER + 1)).toBe(false);
	expect(isSafeJsonInteger(MIN_SAFE_INTEGER - 1)).toBe(false);
	expect(isSafeJsonInteger(1.5)).toBe(false);
	expect(isSafeJsonInteger(Number.NaN)).toBe(false);
	expect(isSafeJsonInteger(Number.POSITIVE_INFINITY)).toBe(false);
	expect(isSafeJsonInteger("7")).toBe(false);
	expect(isSafeJsonInteger(true)).toBe(false);
	expect(isSafeJsonInteger(null)).toBe(false);
});

test("SDK errors expose stable wire codes independent of class names", () => {
	const base = new QgisSdkError("failure");
	expect(base).toBeInstanceOf(Error);
	expect(base).toBeInstanceOf(QgisSdkError);
	expect(base.name).toBe("QgisSdkError");
	expect(base.code).toBe("sdk_error");
	expect(base.message).toBe("failure");

	const declaration = new QgisSdkDeclarationError("bad plugin id");
	expect(declaration).toBeInstanceOf(QgisSdkError);
	expect(declaration.name).toBe("QgisSdkDeclarationError");
	expect(declaration.code).toBe("invalid_declaration");
	expect(declaration.message).toBe("bad plugin id");
});

test("contract validation errors serialize path and validator code metadata only", () => {
	const issue = new QgisSdkValidationIssue(["request", 0, "count"], "int_type");
	expect(issue.path).toEqual(["request", 0, "count"]);
	expect(issue.code).toBe("int_type");
	expect(issue.toJSON()).toEqual({
		path: ["request", 0, "count"],
		code: "int_type",
	});

	const error = new QgisSdkContractValidationError("request", [issue]);
	expect(error).toBeInstanceOf(QgisSdkError);
	expect(error.name).toBe("QgisSdkContractValidationError");
	expect(error.code).toBe("contract_validation_failed");
	expect(error.direction).toBe("request");
	expect(error.message).toBe("Request contract validation failed");
	expect(error.toJSON()).toEqual({
		code: "contract_validation_failed",
		direction: "request",
		issues: [{ path: ["request", 0, "count"], code: "int_type" }],
	});

	const resultError = new QgisSdkContractValidationError("result", []);
	expect(resultError.message).toBe("Result contract validation failed");
});

test("parsePluginDescription accepts valid version 1 descriptions from JSON or objects", () => {
	expect(PLUGIN_DESCRIPTION_SCHEMA_VERSION).toBe(1);

	const raw = {
		schema_version: 1,
		id: "example.tools",
		title: "Example tools",
		actions: [
			{
				id: "zebra",
				title: "Zebra",
				handler: "run_zebra",
				request: {
					type: "object",
					properties: {},
					additionalProperties: false,
				},
				result: { type: "null" },
			},
			{
				id: "alpha",
				title: "Alpha",
				handler: "run_alpha",
				request: {
					type: "object",
					properties: {},
					additionalProperties: false,
				},
				result: { type: "integer" },
			},
		],
	};

	const fromObject = parsePluginDescription(raw);
	const fromJson = parsePluginDescription(JSON.stringify(raw));

	expect(fromObject).toEqual(fromJson);
	expect(fromObject.schema_version).toBe(1);
	expect(fromObject.id).toBe("example.tools");
	expect(fromObject.title).toBe("Example tools");
	expect(fromObject.actions.map((action) => action.id)).toEqual([
		"alpha",
		"zebra",
	]);
	// A description from a host that predates streams reads as having none.
	expect(fromObject.streams).toEqual([]);
});

test("parsePluginDescription reads declared streams in the shared id namespace", () => {
	const request = {
		type: "object",
		properties: {},
		additionalProperties: false,
	};
	const parsed = parsePluginDescription({
		schema_version: 1,
		id: "example.watch",
		title: "Watch",
		actions: [
			{ id: "b", title: "B", handler: "b", request, result: { type: "null" } },
		],
		streams: [
			{
				id: "a",
				title: "A",
				handler: "a",
				request,
				events: { progress: { type: "integer" }, data: { type: "string" } },
			},
		],
	});
	expect(parsed.streams.map((stream) => stream.id)).toEqual(["a"]);
	expect(parsed.streams[0]?.events.data).toEqual({ type: "string" });
	expect(parsed.streams[0]?.events.state).toBeUndefined();
	expect(Object.isFrozen(parsed.streams[0]?.events)).toBe(true);

	const base = { id: "a", title: "A", handler: "a", request };
	const refused: Record<string, unknown>[] = [
		{ streams: "nope" },
		{ streams: [{ ...base, events: {} }] },
		{ streams: [{ ...base, events: { ticks: { type: "integer" } } }] },
		{ streams: [{ ...base, events: { data: "nope" } }] },
		{ streams: [{ ...base, id: "b", events: { data: { type: "null" } } }] },
		{
			streams: [{ ...base, request: null, events: { data: { type: "null" } } }],
		},
	];
	for (const overrides of refused) {
		expect(() =>
			parsePluginDescription({
				schema_version: 1,
				id: "example.watch",
				title: "Watch",
				actions: [
					{
						id: "b",
						title: "B",
						handler: "b",
						request,
						result: { type: "null" },
					},
				],
				...overrides,
			}),
		).toThrow(QgisSdkDeclarationError);
	}
});

test("parsePluginDescription rejects malformed or unsupported plugin descriptions", () => {
	expect(() => parsePluginDescription("{not-json")).toThrow(
		QgisSdkDeclarationError,
	);
	expect(() => parsePluginDescription("null")).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 2,
			id: "demo",
			title: "Demo",
			actions: [],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "1invalid",
			title: "Demo",
			actions: [],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "   ",
			actions: [],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: "not-an-array",
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: ["not-an-object"],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: [
				{
					id: "bad id",
					title: "Ping",
					handler: "ping",
					request: {},
					result: {},
				},
			],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: [
				{
					id: "ping",
					title: "",
					handler: "ping",
					request: {},
					result: {},
				},
			],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: [
				{
					id: "ping",
					title: "Ping",
					handler: "1bad_handler",
					request: {},
					result: {},
				},
			],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: [
				{
					id: "ping",
					title: "Ping",
					handler: "ping",
					request: null,
					result: {},
				},
			],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: [
				{
					id: "ping",
					title: "Ping",
					handler: "ping",
					request: {},
					result: [],
				},
			],
		}),
	).toThrow(QgisSdkDeclarationError);
	expect(() =>
		parsePluginDescription({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: [
				{
					id: "ping",
					title: "Ping",
					handler: "ping",
					request: {},
					result: {},
				},
				{
					id: "ping",
					title: "Ping again",
					handler: "ping_again",
					request: {},
					result: {},
				},
			],
		}),
	).toThrow(QgisSdkDeclarationError);
});

test("isPlainRecord accepts objects and rejects arrays, null and primitives", () => {
	expect(isPlainRecord({})).toBe(true);
	expect(isPlainRecord({ a: 1 })).toBe(true);
	expect(isPlainRecord(Object.create(null))).toBe(true);
	expect(isPlainRecord([])).toBe(false);
	expect(isPlainRecord(null)).toBe(false);
	expect(isPlainRecord(undefined)).toBe(false);
	expect(isPlainRecord("record")).toBe(false);
	expect(isPlainRecord(1)).toBe(false);
});
