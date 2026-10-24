import { expect, test } from "@archont561/bun-test-utils";
import {
	type BridgeClientLike,
	CONTRACT_FINGERPRINT,
	ContractError,
	createOperations,
	type InvokeOptions,
	OPERATIONS,
	PLUGIN_DESCRIPTION_SCHEMA_VERSION,
	PLUGIN_ID,
	SitesDetailsRequest,
	SitesDetailsResult,
	SitesSummaryRequest,
} from "./contracts/generated/clients/sites";

type Sent = {
	readonly operation: string;
	readonly payload: Readonly<Record<string, unknown>> | undefined;
	readonly options: InvokeOptions | undefined;
};

/** A transport that records what the generated client asked for. */
function scripted(reply: unknown): { client: BridgeClientLike; sent: Sent[] } {
	const sent: Sent[] = [];
	return {
		sent,
		client: {
			invoke: (
				operation: string,
				payload?: Readonly<Record<string, unknown>>,
				options?: InvokeOptions,
			) => {
				sent.push({ operation, payload, options });
				return Promise.resolve(reply);
			},
		},
	};
}

const summary = { total: 2, largest: "sites", mode: "fast" };

test("the generated module names the plugin and its description version", () => {
	expect(PLUGIN_ID).toBe("org.example.sites");
	expect(PLUGIN_DESCRIPTION_SCHEMA_VERSION).toBe(1);
	expect(CONTRACT_FINGERPRINT.startsWith("sha256:")).toBe(true);
	expect(CONTRACT_FINGERPRINT.length).toBe("sha256:".length + 64);
});

test("the module lists every declared operation id", () => {
	expect(OPERATIONS).toEqual([
		"sites.details",
		"sites.refresh",
		"sites.summary",
	]);
});

test("the public surface is the generated map, not a generic invoke", () => {
	const operations = createOperations({
		invoke: () => Promise.resolve(summary),
	});
	expect(Object.keys(operations)).toEqual(["sites"]);
	expect("invoke" in operations).toBe(false);
});

test("an input validator is strict about unknown arguments", () => {
	expect(SitesSummaryRequest({ layer_id: "sites" }, true)).toBe(true);
	expect(SitesSummaryRequest({ layer_id: "sites", extra: 1 }, true)).toBe(
		false,
	);
	// The same payload is tolerated when the flag is off, which is how a result
	// validator behaves: additive for responses, closed for arguments.
	expect(SitesSummaryRequest({ layer_id: "sites", extra: 1 })).toBe(true);
});

test("strictness reaches nested input objects", () => {
	const accepted = { layer_id: "sites", options: { limit: 1 } };
	expect(SitesDetailsRequest(accepted, true)).toBe(true);
	expect(
		SitesDetailsRequest({ layer_id: "sites", options: { bogus: 1 } }, true),
	).toBe(false);
});

test("an input validator rejects a wrong type and an unknown enum branch", () => {
	expect(SitesSummaryRequest({ layer_id: 1 }, true)).toBe(false);
	expect(SitesSummaryRequest({ layer_id: "sites", limit: 1.5 }, true)).toBe(
		false,
	);
	expect(SitesSummaryRequest({ layer_id: "sites", mode: "slow" }, true)).toBe(
		false,
	);
});

test("a result validator tolerates a field the host added later", () => {
	const extended = {
		layer_id: "sites",
		field_names: ["a"],
		options: { include_fields: true, limit: 1, future: "ok" },
		added_by_a_newer_host: 1,
	};
	expect(SitesDetailsResult(extended)).toBe(true);
	// Still closed in the one direction that would hide a broken host.
	expect(SitesDetailsResult(extended, true)).toBe(false);
	const { options: _omitted, ...missing } = extended;
	expect(SitesDetailsResult(missing)).toBe(false);
});

test("createOperations sends the declared operation and returns the result", async () => {
	const { client, sent } = scripted(summary);
	const operations = createOperations(client);
	const options: InvokeOptions = {};
	const result = await operations.sites.summary({ layer_id: "sites" }, options);
	expect(result.total).toBe(2);
	expect(sent.length).toBe(1);
	expect(sent[0]?.operation).toBe("sites.summary");
	expect(sent[0]?.payload).toEqual({ layer_id: "sites" });
	expect(sent[0]?.options).toBe(options);
});

test("an action with no declared inputs still invokes with an empty payload", async () => {
	const { client, sent } = scripted(summary);
	await createOperations(client).sites.refresh();
	expect(sent[0]?.operation).toBe("sites.refresh");
	expect(sent[0]?.payload).toEqual({});
});

test("a malformed argument throws before the transport is touched", async () => {
	const { client, sent } = scripted(summary);
	const failing = createOperations(client).sites.summary({
		layer_id: "sites",
		guess: true,
	} as never);
	await expect(failing).rejects.toThrow(ContractError);
	expect(sent.length).toBe(0);
});

test("a malformed response throws instead of leaking a wrong type", async () => {
	const { client } = scripted({
		total: "many",
		largest: "sites",
		mode: "fast",
	});
	const failing = createOperations(client).sites.summary({ layer_id: "sites" });
	await expect(failing).rejects.toThrow(ContractError);
});

test("the error names the operation it failed on", async () => {
	const { client } = scripted({ total: 1 });
	try {
		await createOperations(client).sites.refresh();
	} catch (error) {
		expect(error instanceof ContractError).toBe(true);
		expect((error as ContractError).message).toContain("sites.refresh");
		return;
	}
	throw new Error("expected the result validator to reject the reply");
});
