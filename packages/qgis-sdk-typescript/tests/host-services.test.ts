/**
 * The project and raster namespaces of the generated host client (TASK-87,
 * TASK-88): every operation answers the interface the generator named, and the
 * request it accepts is the closed one it declared.
 *
 * The transport is scripted, so what is under test is the generated surface
 * itself - the validator pair `call` applies to each request and each reply -
 * not a host. The Python side proves the same operations end to end; this file
 * proves a page reads them without a cast.
 */

import { expect, test } from "@archont561/bun-test-utils";
import {
	createHost,
	type FileRef,
	type HostClientLike,
	type HostInvokeOptions,
	QgisSdkHostContractError,
} from "@/host";

type Sent = {
	readonly operation: string;
	readonly payload: Readonly<Record<string, unknown>> | undefined;
};

/** A transport that answers every invoke with the same value and records it. */
function scripted(reply: unknown): {
	readonly client: HostClientLike;
	readonly sent: Sent[];
} {
	const sent: Sent[] = [];
	return {
		sent,
		client: {
			invoke: (
				operation: string,
				payload?: Readonly<Record<string, unknown>>,
				_options?: HostInvokeOptions,
			) => {
				sent.push({ operation, payload });
				return Promise.resolve(reply);
			},
			subscribe: () => Promise.reject(new Error("not used here")),
		},
	};
}

const picked: FileRef = {
	kind: "file",
	id: "0123456789abcdef0123456789abcdef",
	name: "project.qgs",
	operations: ["read", "write"],
};

const tree = {
	nodes: [
		{
			id: "group-root",
			name: "Elevation",
			kind: "group",
			visible: true,
			parent: null,
		},
		{
			id: "points-1",
			name: "points",
			kind: "layer",
			visible: false,
			parent: "group-root",
		},
	],
};

const raster = {
	kind: "raster",
	id: "raster-1",
	name: "elevation",
	band_count: 1,
	data_types: ["Float64"],
	no_data: [-9999],
	extent: { x_min: 21, y_min: 52, x_max: 21.3, y_max: 52.2 },
	resolution: [0.1, 0.1],
	crs: "EPSG:4326",
};

const entry = { key: "project_author", value: "Ada" };
const bookmark = {
	name: "home",
	extent: { x_min: 21, y_min: 52, x_max: 21.2, y_max: 52.2 },
};

// -- the project -------------------------------------------------------------

test("the tree arrives as the flat model a page draws", async () => {
	const { client, sent } = scripted(tree);
	const parsed = await createHost(client).project.tree();

	expect(parsed.nodes[1]?.parent).toBe("group-root");
	expect(parsed.nodes[1]?.visible).toBe(false);
	expect(sent[0]?.operation).toBe("project.tree");
});

test("a mutation answers the tree it produced, in the namespace's own ids", async () => {
	const { client, sent } = scripted(tree);
	const operations = createHost(client);

	const added = await operations.project.add_layer({
		layer_id: "points-1",
		group: "group-root",
	});
	const moved = await operations.project.move_layer({
		layer_id: "points-1",
		group: "group-root",
		index: 0,
	});
	const hidden = await operations.project.set_visible({
		node_id: "group-root",
		visible: false,
	});
	const removed = await operations.project.remove_layer({
		layer_id: "points-1",
	});

	expect(added.nodes.length).toBe(2);
	expect(moved.nodes[1]?.kind).toBe("layer");
	expect(hidden.nodes[0]?.visible).toBe(true);
	expect(removed.nodes[0]?.id).toBe("group-root");
	expect(sent.map((call) => call.operation)).toEqual([
		"project.add_layer",
		"project.move_layer",
		"project.set_visible",
		"project.remove_layer",
	]);
	expect(sent[0]?.payload).toEqual({
		layer_id: "points-1",
		group: "group-root",
	});
});

test("the project CRS is a string that a set made, or null", async () => {
	const { client } = scripted("EPSG:3857");
	const operations = createHost(client);

	await expect(operations.project.crs()).resolves.toBe("EPSG:3857");
	await expect(
		operations.project.set_crs({ auth_id: "EPSG:3857" }),
	).resolves.toBe("EPSG:3857");

	const { client: empty } = scripted(null);
	await expect(createHost(empty).project.crs()).resolves.toBeNull();
});

test("variables and properties are one key/value model on the wire", async () => {
	const { client, sent } = scripted([entry]);
	const operations = createHost(client);

	await expect(operations.project.variables()).resolves.toEqual([entry]);
	await expect(
		operations.project.set_variable({ name: "project_author", value: "Ada" }),
	).resolves.toEqual([entry]);
	await expect(
		operations.project.unset_variable({ name: "project_author" }),
	).resolves.toEqual([entry]);
	await expect(operations.project.properties()).resolves.toEqual([entry]);
	await expect(
		operations.project.set_property({ name: "project_author", value: "Ada" }),
	).resolves.toEqual([entry]);
	await expect(
		operations.project.unset_property({ name: "project_author" }),
	).resolves.toEqual([entry]);
	expect(sent.map((call) => call.operation)).toEqual([
		"project.variables",
		"project.set_variable",
		"project.unset_variable",
		"project.properties",
		"project.set_property",
		"project.unset_property",
	]);
});

test("a bookmark carries its extent and is removed by name", async () => {
	const { client, sent } = scripted([bookmark]);
	const operations = createHost(client);

	await expect(operations.project.bookmarks()).resolves.toEqual([bookmark]);
	const one = scripted(bookmark);
	await expect(
		createHost(one.client).project.bookmark({ name: "home" }),
	).resolves.toEqual(bookmark);
	await expect(
		operations.project.add_bookmark({
			name: "home",
			extent: bookmark.extent,
		}),
	).resolves.toEqual([bookmark]);
	await expect(
		operations.project.remove_bookmark({ name: "home" }),
	).resolves.toEqual([bookmark]);
	expect(sent[1]?.payload).toEqual({ name: "home", extent: bookmark.extent });
});

test("the file operations take a host-minted ref, never a path", async () => {
	const { client, sent } = scripted({ path: "/projects/read.qgs" });
	const operations = createHost(client);

	await createHost(scripted(tree).client).project.read({ file: picked });
	const written = await operations.project.write({ file: picked });
	const saved = await operations.project.save();

	expect(written.path).toBe("/projects/read.qgs");
	expect(saved.path).toBe("/projects/read.qgs");
	// A path string is not a ref: the branded handle is refused before the call.
	await expect(
		operations.project.write({ file: "/tmp/project.qgs" } as never),
	).rejects.toThrow(QgisSdkHostContractError);
	expect(sent.map((call) => call.operation)).toEqual([
		"project.write",
		"project.save",
	]);
});

test("a layer page and an id page stay the shapes they declare", async () => {
	const { client } = scripted({ items: ["points-1"], truncated: false });

	await expect(createHost(client).project.layer_ids()).resolves.toEqual({
		items: ["points-1"],
		truncated: false,
	});
});

test("a tree the host should not have produced is refused", async () => {
	const broken = { nodes: [{ ...tree.nodes[0], kind: "surface" }] };
	const { client } = scripted(broken);

	await expect(createHost(client).project.tree()).rejects.toThrow(
		QgisSdkHostContractError,
	);
});

// -- rasters -----------------------------------------------------------------

test("a raster crosses with its bands, extent and CRS", async () => {
	const { client, sent } = scripted(raster);
	const operations = createHost(client);

	const opened = await operations.rasters.open({ file: picked });
	const read = await operations.rasters.get({ layer_id: "raster-1" });

	expect(opened.band_count).toBe(1);
	expect(read.data_types).toEqual(["Float64"]);
	expect(read.extent.x_max).toBe(21.3);
	expect(sent.map((call) => call.operation)).toEqual([
		"rasters.open",
		"rasters.get",
	]);
});

test("statistics name the band they measured", async () => {
	const statistics = {
		band: 1,
		minimum: 1,
		maximum: 6,
		mean: 3.2,
		std_dev: 1.9235384061671346,
		valid_count: 5,
		no_data_count: 1,
	};
	const { client, sent } = scripted(statistics);

	const measured = await createHost(client).rasters.statistics({
		layer_id: "raster-1",
		band: 1,
	});

	expect(measured.mean).toBe(3.2);
	expect(measured.no_data_count).toBe(1);
	expect(sent[0]?.payload).toEqual({ layer_id: "raster-1", band: 1 });
});

test("a sample answers one value per band, no-data included", async () => {
	const sample = {
		point: { x: 21.05, y: 52.15, crs: "EPSG:4326" },
		values: [1, null],
	};
	const { client, sent } = scripted(sample);

	const read = await createHost(client).rasters.sample({
		layer_id: "raster-1",
		point: { x: 130000, y: 6150000, crs: "EPSG:3857" },
		band: 2,
	});

	expect(read.values).toEqual([1, null]);
	expect(read.point.crs).toBe("EPSG:4326");
	expect(sent[0]?.payload).toEqual({
		layer_id: "raster-1",
		point: { x: 130000, y: 6150000, crs: "EPSG:3857" },
		band: 2,
	});
});

test("a raster reply without a kind is refused, not half read", async () => {
	const { kind: _dropped, ...kindless } = raster;
	const { client } = scripted(kindless);

	await expect(
		createHost(client).rasters.get({ layer_id: "raster-1" }),
	).rejects.toThrow(QgisSdkHostContractError);
});
