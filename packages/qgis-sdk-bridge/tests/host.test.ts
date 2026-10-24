import { expect, test } from "@archont561/bun-test-utils";
import {
	createHost,
	HOST_FINGERPRINT,
	HOST_ID,
	HOST_OPERATIONS,
	HOST_SCHEMA_VERSION,
	type HostClientLike,
	HostContractError,
	type HostInvokeOptions,
	PageRequest,
	type VectorLayerInfo,
} from "@/host";

type Sent = {
	readonly operation: string;
	readonly payload: Readonly<Record<string, unknown>> | undefined;
	readonly options: HostInvokeOptions | undefined;
};

function scripted(reply: unknown): { client: HostClientLike; sent: Sent[] } {
	const sent: Sent[] = [];
	return {
		sent,
		client: {
			invoke: (
				operation: string,
				payload?: Readonly<Record<string, unknown>>,
				options?: HostInvokeOptions,
			) => {
				sent.push({ operation, payload, options });
				return Promise.resolve(reply);
			},
		},
	};
}

const sites: VectorLayerInfo = {
	id: "sites",
	name: "Sites",
	geometry_type: "point",
	field_names: ["id", "name"],
	crs: "EPSG:4326",
};

const page = { items: [sites], truncated: false };

test("the host module names its surface and advertises its version", () => {
	expect(HOST_ID).toBe("qgis.host");
	expect(HOST_SCHEMA_VERSION).toBe(1);
	expect(HOST_FINGERPRINT.startsWith("sha256:")).toBe(true);
	expect(HOST_OPERATIONS).toEqual([
		"layers.get",
		"layers.list",
		"notifications.info",
		"project.layer_ids",
		"settings.get",
		"styles.apply",
	]);
});

test("a read is sent as the declared operation and validated on the way back", async () => {
	const { client, sent } = scripted(page);
	const result = await createHost(client).layers.list({ limit: 1 });
	expect(result.items[0]?.id).toBe("sites");
	expect(sent[0]?.operation).toBe("layers.list");
	expect(sent[0]?.payload).toEqual({ limit: 1 });
});

test("an operation with no inputs still sends an empty payload", async () => {
	const { client, sent } = scripted(page);
	await createHost(client).layers.list();
	expect(sent[0]?.payload).toEqual({});
});

test("a declared bound is refused before the transport is touched", async () => {
	const { client, sent } = scripted(page);
	const tooLarge = createHost(client).layers.list({ limit: 500 } as never);
	await expect(tooLarge).rejects.toThrow(HostContractError);
	expect(sent.length).toBe(0);
});

test("an unknown argument never reaches the host", async () => {
	const { client, sent } = scripted(sites);
	const failing = createHost(client).layers.get({
		layer_id: "sites",
		pick: "first",
	} as never);
	await expect(failing).rejects.toThrow(HostContractError);
	expect(sent.length).toBe(0);
});

test("a result the host should not have produced is refused, not returned", async () => {
	const malformed = { ...sites, geometry_type: "surface" };
	const { client } = scripted(malformed);
	await expect(
		createHost(client).layers.get({ layer_id: "sites" }),
	).rejects.toThrow(HostContractError);
});

test("an added field on a result is tolerated, an absent one is not", async () => {
	const extended = { ...page, total: 1 };
	const { client } = scripted(extended);
	const result = await createHost(client).layers.list();
	expect(result.items.length).toBe(1);

	const { client: broken } = scripted({ items: [sites] });
	await expect(createHost(broken).layers.list()).rejects.toThrow(
		HostContractError,
	);
});

test("the null result of a mutation is validated as null", async () => {
	const { client, sent } = scripted(null);
	const operations = createHost(client);
	expect(await operations.notifications.info({ message: "hi" })).toBe(null);
	expect(sent[0]?.operation).toBe("notifications.info");

	const { client: wrong } = scripted({ ok: true });
	await expect(
		createHost(wrong).notifications.info({ message: "hi" }),
	).rejects.toThrow(HostContractError);
});

test("a setting may be absent, and that is not an error", async () => {
	const { client } = scripted(null);
	expect(await createHost(client).settings.get({ key: "theme" })).toBe(null);
	const { client: stored } = scripted("dark");
	expect(await createHost(stored).settings.get({ key: "theme" })).toBe("dark");
});

test("a paged id list is a list of strings and nothing else", async () => {
	const { client } = scripted({
		items: ["a", "b"],
		truncated: true,
		next_cursor: "2",
	});
	const result = await createHost(client).project.layer_ids({ limit: 2 });
	expect(result.next_cursor).toBe("2");
	const { client: numbered } = scripted({ items: [1, 2], truncated: false });
	await expect(createHost(numbered).project.layer_ids()).rejects.toThrow(
		HostContractError,
	);
});

test("the error names the host operation it failed on", async () => {
	const { client } = scripted({ items: "everything", truncated: false });
	try {
		await createHost(client).layers.list();
	} catch (error) {
		expect(error instanceof HostContractError).toBe(true);
		expect((error as HostContractError).message).toContain("layers.list");
		return;
	}
	throw new Error("expected the page validator to reject the reply");
});

test("the generated PageRequest refuses a cursor the host did not issue", () => {
	expect(PageRequest({ cursor: "12" }, true)).toBe(true);
	expect(PageRequest({ limit: 5 }, true)).toBe(true);
	for (const cursor of ["abc", "-1", "1 ", "", "12a"]) {
		expect(PageRequest({ cursor }, true)).toBe(false);
	}
});
