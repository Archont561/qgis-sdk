import { expect, test } from "@archont561/bun-test-utils";
import { QgisSdkError } from "@";
import {
	type AlgorithmInfo,
	type AlgorithmSummary,
	createHost,
	type FileRef,
	HOST_FINGERPRINT,
	HOST_ID,
	HOST_OPERATIONS,
	HOST_SCHEMA_VERSION,
	type HostClientLike,
	type HostInvokeOptions,
	type HostStreamHandle,
	type HostStreamTerminal,
	type NetworkFetchEvent,
	PageRequest,
	type ParameterInfo,
	QgisSdkHostContractError,
	type RunOutput,
	type VectorLayerInfo,
} from "@/host";

type Sent = {
	readonly operation: string;
	readonly payload: Readonly<Record<string, unknown>> | undefined;
	readonly options: HostInvokeOptions | undefined;
};

type Scripted = {
	readonly client: HostClientLike;
	readonly sent: Sent[];
	readonly emit: (event: { kind: string; payload: unknown }) => void;
	readonly end: (terminal: HostStreamTerminal) => void;
	readonly closed: () => number;
};

function scripted(reply: unknown): Scripted {
	const sent: Sent[] = [];
	let handlers: Parameters<HostClientLike["subscribe"]>[2];
	let closed = 0;
	return {
		sent,
		closed: () => closed,
		emit: (event) => {
			handlers?.onEvent?.(event as never);
		},
		end: (terminal) => {
			handlers?.onTerminal?.(terminal);
		},
		client: {
			invoke: (
				operation: string,
				payload?: Readonly<Record<string, unknown>>,
				options?: HostInvokeOptions,
			) => {
				sent.push({ operation, payload, options });
				return Promise.resolve(reply);
			},
			subscribe: (operation, payload, given, options) => {
				sent.push({ operation, payload, options });
				handlers = given;
				const handle: HostStreamHandle = {
					id: "s1",
					get closed() {
						return closed > 0;
					},
					close: () => {
						closed += 1;
						given?.onTerminal?.({ kind: "disposed" });
					},
				};
				return Promise.resolve(handle);
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
		"algorithms.describe",
		"algorithms.list",
		"algorithms.providers",
		"algorithms.run",
		"blob.get",
		"editing.add",
		"editing.begin",
		"editing.commit",
		"editing.delete",
		"editing.rollback",
		"editing.update",
		"expressions.evaluate",
		"expressions.validate",
		"features.get",
		"features.page",
		"files.export",
		"layers.get",
		"layers.list",
		"layers.open_vector",
		"network.fetch",
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
	await expect(tooLarge).rejects.toThrow(QgisSdkHostContractError);
	expect(sent.length).toBe(0);
});

test("an unknown argument never reaches the host", async () => {
	const { client, sent } = scripted(sites);
	const failing = createHost(client).layers.get({
		layer_id: "sites",
		pick: "first",
	} as never);
	await expect(failing).rejects.toThrow(QgisSdkHostContractError);
	expect(sent.length).toBe(0);
});

test("a result the host should not have produced is refused, not returned", async () => {
	const malformed = { ...sites, geometry_type: "surface" };
	const { client } = scripted(malformed);
	await expect(
		createHost(client).layers.get({ layer_id: "sites" }),
	).rejects.toThrow(QgisSdkHostContractError);
});

test("an added field on a result is tolerated, an absent one is not", async () => {
	const extended = { ...page, total: 1 };
	const { client } = scripted(extended);
	const result = await createHost(client).layers.list();
	expect(result.items.length).toBe(1);

	const { client: broken } = scripted({ items: [sites] });
	await expect(createHost(broken).layers.list()).rejects.toThrow(
		QgisSdkHostContractError,
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
	).rejects.toThrow(QgisSdkHostContractError);
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
		QgisSdkHostContractError,
	);
});

test("the error names the host operation it failed on", async () => {
	const { client } = scripted({ items: "everything", truncated: false });
	try {
		await createHost(client).layers.list();
	} catch (error) {
		expect(error instanceof QgisSdkHostContractError).toBe(true);
		expect((error as QgisSdkHostContractError).message).toContain(
			"layers.list",
		);
		return;
	}
	throw new Error("expected the page validator to reject the reply");
});

test("the host contract error is one of the package's errors, by class and by code", async () => {
	const { client } = scripted({ items: "everything", truncated: false });
	const failing = createHost(client).layers.list();
	await expect(failing).rejects.toBeInstanceOf(QgisSdkError);
	await expect(failing).rejects.toMatchObject({
		name: "QgisSdkHostContractError",
		code: "contract_validation_failed",
		operation: "layers.list",
	});
});

test("the generated PageRequest refuses a cursor the host did not issue", () => {
	expect(PageRequest({ cursor: "12" }, true)).toBe(true);
	expect(PageRequest({ limit: 5 }, true)).toBe(true);
	for (const cursor of ["abc", "-1", "1 ", "", "12a"]) {
		expect(PageRequest({ cursor }, true)).toBe(false);
	}
});

// -- scoped authority: file refs and the fetch stream (TASK-20) -------------

const picked: FileRef = {
	kind: "file",
	id: "0123456789abcdef0123456789abcdef",
	name: "sites.geojson",
	operations: ["read"],
};

test("an open takes a host-minted file ref and never a path", async () => {
	const { client, sent } = scripted(sites);
	const opened = await createHost(client).layers.open_vector({ file: picked });
	expect(opened.id).toBe("sites");
	expect(sent[0]?.operation).toBe("layers.open_vector");
	expect(sent[0]?.payload).toEqual({ file: picked });

	const { client: pathClient, sent: pathSent } = scripted(sites);
	const failing = createHost(pathClient).layers.open_vector({
		file: "/home/me/sites.geojson",
	} as never);
	await expect(failing).rejects.toThrow(QgisSdkHostContractError);
	const otherKind = createHost(pathClient).layers.open_vector({
		file: { kind: "layer", id: picked.id },
	} as never);
	await expect(otherKind).rejects.toThrow(QgisSdkHostContractError);
	const noId = createHost(pathClient).layers.open_vector({
		file: { kind: "file", id: "not hex" },
	} as never);
	await expect(noId).rejects.toThrow(QgisSdkHostContractError);
	expect(pathSent.length).toBe(0);
});

test("an export sends the ref and the text and reads back the size", async () => {
	const { client, sent } = scripted({ bytes_written: 4, name: "out.csv" });
	const result = await createHost(client).files.export({
		file: { ...picked, name: "out.csv", operations: ["write"] },
		content: "a,b\n",
	});
	expect(result.bytes_written).toBe(4);
	expect(sent[0]?.operation).toBe("files.export");

	const { client: wrong } = scripted({ bytes_written: "4" });
	await expect(
		createHost(wrong).files.export({ file: picked, content: "x" }),
	).rejects.toThrow(QgisSdkHostContractError);
});

test("a fetch is a stream that delivers one typed response and ends", async () => {
	const scripted_ = scripted(null);
	const events: NetworkFetchEvent[] = [];
	const ends: HostStreamTerminal[] = [];
	const handle = await createHost(scripted_.client).network.fetch(
		{
			url: "https://api.example.org/collections",
			headers: [{ name: "Accept", value: "application/json" }],
		},
		{
			onEvent: (event) => {
				events.push(event);
			},
			onTerminal: (terminal) => {
				ends.push(terminal);
			},
		},
	);
	expect(scripted_.sent[0]?.operation).toBe("network.fetch");
	const response = {
		url: "https://api.example.org/collections",
		status_code: 200,
		reason: "OK",
		headers: [{ name: "Content-Type", value: "application/json" }],
		text: "{}",
		base64: null,
	};
	scripted_.emit({ kind: "data", payload: response });
	scripted_.end({ kind: "complete" });
	expect(events).toEqual([{ kind: "data", payload: response }]);
	expect(ends).toEqual([{ kind: "complete" }]);
	expect(handle.closed).toBe(false);
});

test("a fetch request outside the declaration never reaches the host", async () => {
	const scripted_ = scripted(null);
	const host = createHost(scripted_.client);
	await expect(
		host.network.fetch(
			{ url: "https://a.example.org", method: "FETCH" } as never,
			{},
		),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		host.network.fetch(
			{ url: "https://a.example.org", timeout_seconds: 0 },
			{},
		),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		host.network.fetch(
			{ url: "https://a.example.org", headers: ["Accept: x"] } as never,
			{},
		),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(scripted_.sent.length).toBe(0);
});

test("a response the host should not have produced ends the fetch as an error", async () => {
	const scripted_ = scripted(null);
	const ends: HostStreamTerminal[] = [];
	await createHost(scripted_.client).network.fetch(
		{ url: "https://api.example.org/x" },
		{
			onTerminal: (terminal) => {
				ends.push(terminal);
			},
		},
	);
	scripted_.emit({ kind: "data", payload: { status_code: "200" } });
	expect(ends.length).toBe(1);
	expect(ends[0]?.kind).toBe("error");
	expect(ends[0]?.message).toContain("network.fetch");
	expect(scripted_.closed()).toBe(1);
});

const distance: ParameterInfo = {
	name: "DISTANCE",
	label: "Distance",
	description: "",
	kind: "distance",
	required: true,
	optional: false,
	advanced: false,
	hidden: false,
	destination: false,
	multiple: false,
	default_json: "10.0",
	options: [],
	minimum: null,
	maximum: 1e6,
	number_type: "double",
	extension: null,
};

const bufferInfo: AlgorithmInfo = {
	id: "native:buffer",
	provider: "native",
	name: "buffer",
	label: "Buffer",
	group: "Vector geometry",
	group_id: "vectorgeometry",
	help: "Buffers the features.",
	deprecated: false,
	parameters: [distance],
	outputs: [{ name: "OUTPUT", label: "Buffered", kind: "outputVector" }],
};

test("the providers and the algorithm list are paged like every other list", async () => {
	const providers = scripted({
		items: [{ id: "native", label: "QGIS (native c++)", version: "4.2.3" }],
		truncated: false,
	});
	const first = await createHost(providers.client).algorithms.providers();
	expect(first.items[0]?.id).toBe("native");
	expect(providers.sent[0]?.operation).toBe("algorithms.providers");
	expect(providers.sent[0]?.payload).toEqual({});

	const summary: AlgorithmSummary = {
		id: "native:buffer",
		provider: "native",
		name: "buffer",
		label: "Buffer",
		group: "Vector geometry",
		deprecated: false,
	};
	const list = scripted({
		items: [summary],
		truncated: true,
		next_cursor: "1",
	});
	const result = await createHost(list.client).algorithms.list({
		provider: "native",
		limit: 1,
	});
	expect(result.items[0]?.label).toBe("Buffer");
	expect(result.next_cursor).toBe("1");
	expect(list.sent[0]?.operation).toBe("algorithms.list");
	expect(list.sent[0]?.payload).toEqual({ provider: "native", limit: 1 });

	const tooLarge = createHost(list.client).algorithms.list({
		limit: 500,
	} as never);
	await expect(tooLarge).rejects.toThrow(QgisSdkHostContractError);
	expect(list.sent.length).toBe(1);

	const { client: badProvider } = scripted({
		items: [{ id: "native", label: "QGIS", version: 4 }],
		truncated: false,
	});
	await expect(createHost(badProvider).algorithms.providers()).rejects.toThrow(
		QgisSdkHostContractError,
	);
	const { client: badSummary } = scripted({
		items: [{ ...summary, deprecated: "no" }],
		truncated: false,
	});
	await expect(createHost(badSummary).algorithms.list()).rejects.toThrow(
		QgisSdkHostContractError,
	);
});

test("a description carries typed parameters and outputs, and nothing looser", async () => {
	const { client, sent } = scripted(bufferInfo);
	const info = await createHost(client).algorithms.describe({
		algorithm_id: "native:buffer",
	});
	expect(info.parameters[0]?.maximum).toBe(1e6);
	expect(info.parameters[0]?.default_json).toBe("10.0");
	expect(info.outputs[0]?.kind).toBe("outputVector");
	expect(sent[0]?.operation).toBe("algorithms.describe");
	expect(sent[0]?.payload).toEqual({ algorithm_id: "native:buffer" });

	const describe = (reply: unknown) =>
		createHost(scripted(reply).client).algorithms.describe({
			algorithm_id: "native:buffer",
		});
	await expect(
		describe({ ...bufferInfo, parameters: [{ ...distance, minimum: "0" }] }),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		describe({ ...bufferInfo, parameters: [{ ...distance, options: [1] }] }),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		describe({
			...bufferInfo,
			outputs: [{ name: "OUTPUT", kind: "outputVector" }],
		}),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(describe({ ...bufferInfo, deprecated: 0 })).rejects.toThrow(
		QgisSdkHostContractError,
	);
	const { id: _id, ...withoutId } = bufferInfo;
	await expect(describe(withoutId)).rejects.toThrow(QgisSdkHostContractError);

	const { client: unsent, sent: nothing } = scripted(bufferInfo);
	await expect(
		createHost(unsent).algorithms.describe({} as never),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(nothing.length).toBe(0);
});

test("a run sends the id and the params and reads back tagged outputs", async () => {
	const outputs: RunOutput[] = [
		{ name: "OUTPUT", kind: "vector", layer: sites },
		{ name: "REPORT", kind: "file", file: picked },
		{ name: "COUNT", kind: "value", value: 3 },
		{ name: "MEAN", kind: "value", value: null },
	];
	const { client, sent } = scripted({ algorithm: "native:buffer", outputs });
	const result = await createHost(client).algorithms.run({
		algorithm_id: "native:buffer",
		params: { INPUT: "sites", DISTANCE: 25 },
	});
	expect(result.outputs.length).toBe(4);
	expect(result.outputs[0]?.layer?.id).toBe("sites");
	expect(sent[0]?.operation).toBe("algorithms.run");
	expect(sent[0]?.payload).toEqual({
		algorithm_id: "native:buffer",
		params: { INPUT: "sites", DISTANCE: 25 },
	});

	const run = (reply: unknown) =>
		createHost(scripted(reply).client).algorithms.run({
			algorithm_id: "native:buffer",
			params: {},
		});
	await expect(
		run({
			algorithm: "native:buffer",
			outputs: [{ name: "X", kind: "raster" }],
		}),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		run({
			algorithm: "native:buffer",
			outputs: [{ name: "X", kind: "value", value: {} }],
		}),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		run({
			algorithm: "native:buffer",
			outputs: [{ name: "X", kind: "file", file: "/tmp/x" }],
		}),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		run({
			algorithm: "native:buffer",
			outputs: [{ name: "X", kind: "vector", layer: {} }],
		}),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(run({ algorithm: "native:buffer" })).rejects.toThrow(
		QgisSdkHostContractError,
	);
	await expect(run({ algorithm: 7, outputs: [] })).rejects.toThrow(
		QgisSdkHostContractError,
	);

	const { client: unsent, sent: nothing } = scripted(null);
	await expect(
		createHost(unsent).algorithms.run({
			algorithm_id: "native:buffer",
		} as never),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		createHost(unsent).algorithms.run({
			algorithm_id: "native:buffer",
			params: [],
		} as never),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(nothing.length).toBe(0);
});

// -- features, expressions and editing (TASK-86) -----------------------------

const geometry = {
	encoding: "wkt",
	value: "POINT (21 52)",
	geometry_type: "point",
	crs: "EPSG:4326",
	part_count: 1,
	vertex_count: 1,
	is_empty: false,
} as const;

test("a feature crosses with its encoded geometry and its attributes", async () => {
	const feature = {
		id: 3,
		attributes: { name: "C", area: 30 },
		geometry,
	};
	const { client, sent } = scripted(feature);
	const result = await createHost(client).features.get({
		layer_id: "parcels",
		feature_id: 3,
		encoding: "wkt",
	});

	expect(sent[0]?.operation).toBe("features.get");
	expect(sent[0]?.payload).toEqual({
		layer_id: "parcels",
		feature_id: 3,
		encoding: "wkt",
	});
	expect(result.geometry?.geometry_type).toBe("point");
	expect(result.attributes).toEqual({ name: "C", area: 30 });

	// ``geometry`` is optional - a page may ask for attributes alone - but an id
	// that is not an integer is not a feature.
	const { client: without } = scripted({ id: "3", attributes: {} });
	await expect(
		createHost(without).features.get({ layer_id: "parcels", feature_id: 3 }),
	).rejects.toThrow(QgisSdkHostContractError);
});

test("a page of features is a stream under the same paging rules", async () => {
	const { client, sent, emit, end, closed } = scripted(null);
	const pages: unknown[] = [];

	const handle = await createHost(client).features.page(
		{ layer_id: "parcels", limit: 100, encoding: "geojson" },
		{
			onEvent: (event) => pages.push(event.payload),
			onTerminal: () => undefined,
		},
	);

	expect(sent[0]?.operation).toBe("features.page");
	expect(sent[0]?.payload).toEqual({
		layer_id: "parcels",
		limit: 100,
		encoding: "geojson",
	});
	emit({
		kind: "data",
		payload: {
			items: [{ id: 1, attributes: {}, geometry: null }],
			truncated: true,
			next_cursor: "1",
		},
	});
	end({ kind: "complete" });
	expect(pages).toHaveLength(1);

	handle.close();
	expect(closed()).toBe(1);

	// The bound the schema declares is checked before anything is sent.
	const { client: unsent, sent: nothing } = scripted(null);
	await expect(
		createHost(unsent).features.page(
			{ layer_id: "parcels", limit: 5000 } as never,
			{},
		),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(nothing.length).toBe(0);
});

test("an expression is a value or a message, and the validator says which", async () => {
	const { client } = scripted({ valid: true, value: 42, message: null });
	const value = await createHost(client).expressions.evaluate({ text: "42" });
	expect(value.valid).toBe(true);
	expect(value.value).toBe(42);

	const { client: broken } = scripted({
		valid: false,
		value: null,
		message: "1 + is not an expression",
	});
	const outcome = await createHost(broken).expressions.evaluate({
		text: "1 +",
	});
	expect(outcome.valid).toBe(false);
	expect(outcome.message).toContain("1 +");

	const { client: checked } = scripted({
		valid: true,
		message: null,
		referenced_columns: ["area"],
	});
	const check = await createHost(checked).expressions.validate({
		text: '"area" > 25',
		layer_id: "parcels",
	});
	expect(check.referenced_columns).toEqual(["area"]);
});

test("an editing session is begun, written and committed as declared", async () => {
	const { client, sent } = scripted({
		session_id: "edit-1",
		layer_id: "parcels",
	});
	const host = createHost(client);
	const opened = await host.editing.begin({ layer_id: "parcels" });
	expect(opened.session_id).toBe("edit-1");

	const { client: addedClient, sent: additions } = scripted({
		feature_id: 9,
		pending: 1,
	});
	const added = await createHost(addedClient).editing.add({
		session_id: "edit-1",
		attributes: { name: "F" },
		geometry,
	});
	expect(added.feature_id).toBe(9);
	expect(additions[0]?.operation).toBe("editing.add");

	const { client: committedClient, sent: commits } = scripted({
		applied: 1,
		feature_ids: [9],
		committed: true,
	});
	const outcome = await createHost(committedClient).editing.commit({
		session_id: "edit-1",
	});
	expect(outcome.committed).toBe(true);
	expect(outcome.feature_ids).toEqual([9]);
	expect(commits[0]?.operation).toBe("editing.commit");
	expect(sent[0]?.operation).toBe("editing.begin");

	const { client: refused } = scripted({
		applied: 0,
		feature_ids: [],
		committed: "yes",
	});
	await expect(
		createHost(refused).editing.commit({ session_id: "edit-1" }),
	).rejects.toThrow(QgisSdkHostContractError);

	const { client: unsent, sent: nothing } = scripted(null);
	await expect(
		createHost(unsent).editing.begin({ layer_id: 7 } as never),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(nothing.length).toBe(0);
});

const blobRef = {
	kind: "blob",
	id: "0123456789abcdef",
	size: 4,
	media_type: "text/plain",
	checksum: "a".repeat(64),
	expires_at: null,
} as const;

test("a blob is fetched by reference and arrives as a checked chunk", async () => {
	const chunk = {
		offset: 0,
		length: 4,
		size: 4,
		media_type: "text/plain",
		checksum: "a".repeat(64),
		data_base64: "AAAA",
		next_offset: 4,
	};
	const { client, sent } = scripted(chunk);
	const got = await createHost(client).blob.get({
		blob: blobRef,
		offset: 0,
		length: 4,
	});

	expect(sent[0]?.operation).toBe("blob.get");
	expect(sent[0]?.payload).toEqual({ blob: blobRef, offset: 0, length: 4 });
	expect(got.next_offset).toBe(4);

	// A reference whose checksum is not a digest, and a chunk with no bytes in
	// it, are refused: the page never reads past the reference it was given.
	const { client: unsent, sent: nothing } = scripted(null);
	await expect(
		createHost(unsent).blob.get({ blob: { ...blobRef, checksum: "abc" } }),
	).rejects.toThrow(QgisSdkHostContractError);
	await expect(
		createHost(scripted({ ...chunk, data_base64: 7 }).client).blob.get({
			blob: blobRef,
		}),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(nothing.length).toBe(0);
});

test("updating and deleting a feature are pending writes, not committed ones", async () => {
	const { client, sent } = scripted({ session_id: "edit-1", pending: 2 });
	const host = createHost(client);

	const updated = await host.editing.update({
		session_id: "edit-1",
		feature_id: 9,
		attributes: { name: "F" },
	});
	expect(updated.pending).toBe(2);
	expect(sent[0]?.operation).toBe("editing.update");

	const deleted = await host.editing.delete({
		session_id: "edit-1",
		feature_id: 9,
	});
	expect(deleted.pending).toBe(2);
	expect(sent[1]?.operation).toBe("editing.delete");

	const rolledBack = await host.editing.rollback({ session_id: "edit-1" });
	expect(rolledBack.pending).toBe(2);
	expect(sent[2]?.operation).toBe("editing.rollback");

	// Nothing is sent when the write names a feature by something other than a
	// feature id.
	const { client: unsent, sent: nothing } = scripted(null);
	await expect(
		createHost(unsent).editing.delete({
			session_id: "edit-1",
			feature_id: "9",
		} as never),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(nothing.length).toBe(0);
});

test("a style is applied to a layer and the call answers with nothing", async () => {
	const { client, sent } = scripted(null);
	const answered = await createHost(client).styles.apply({
		layer_id: "parcels",
		style: "<qgis></qgis>",
	});

	expect(answered).toBe(null);
	expect(sent[0]?.operation).toBe("styles.apply");
	expect(sent[0]?.payload).toEqual({
		layer_id: "parcels",
		style: "<qgis></qgis>",
	});
});
