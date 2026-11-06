/**
 * Compile-time half of the generated host surface (decision-27).
 *
 * Never executed: `tsc --noEmit` over `tests` is the assertion, so a generator
 * that loosened the host types would have to delete a comment to do it.
 */
import {
	createHost,
	HOST_OPERATIONS,
	type HostClientLike,
	type HostOperationId,
	type HostOperations,
	type LayerPage,
	type RasterLayerInfo,
	type VectorLayerInfo,
} from "@/host";

declare const client: HostClientLike;
const operations: HostOperations = createHost(client);
void operations;

// A host operation id is one of the declared literals.
const listed: HostOperationId = "layers.list";
void listed;
// @ts-expect-error `layers.destroy` is not part of the host surface.
const removed: HostOperationId = "layers.destroy";
void removed;
void HOST_OPERATIONS;

// The map is a namespace tree: there is no flat `invoke` and no guessing.
// @ts-expect-error The generated map exposes namespaces, not a generic invoke.
void operations.invoke;
// @ts-expect-error `layers.listAll` is not a declared operation.
void operations.layers.listAll;

// A required argument stays required.
// @ts-expect-error `layer_id` is required by the declaration.
void operations.layers.get({});
// @ts-expect-error `message` is required by the declaration.
void operations.notifications.info();

// An argument keeps its declared type.
void operations.layers.get({
	// @ts-expect-error `layer_id` is a string, not a number.
	layer_id: 7,
});

// A result carries the interface the generator named, not a bare record.
const page = operations.layers.list();
const typed: Promise<LayerPage> = page;
void typed;
// @ts-expect-error A page's items are layer infos, never a list of strings.
const wrongItems: Promise<readonly string[]> = page;

// Every kind of layer crosses the wire, so a union of titled interfaces renders
// as those interfaces and not as a pair of open maps (TASK-87, TASK-91).
declare const anyLayer: Awaited<ReturnType<typeof operations.layers.get>>;
void (anyLayer.kind satisfies
	| "vector"
	| "raster"
	| "mesh"
	| "point_cloud"
	| "vector_tile"
	| "annotation"
	| "tiled_scene");
if (anyLayer.kind === "raster") {
	const bands: number = anyLayer.band_count;
	void bands;
} else if (anyLayer.kind === "mesh") {
	// A mesh answers its own counts, and the union narrows to them.
	const vertices: number = anyLayer.vertex_count;
	const faces: number = anyLayer.face_count;
	const groups: number = anyLayer.group_count;
	// @ts-expect-error A mesh has no field names to offer.
	void anyLayer.field_names;
	void [vertices, faces, groups];
} else if (anyLayer.kind === "point_cloud") {
	const points: number = anyLayer.point_count;
	const attributes: readonly string[] = anyLayer.attribute_names;
	void [points, attributes];
} else if (anyLayer.kind === "vector_tile") {
	const zooms: readonly number[] = [anyLayer.min_zoom, anyLayer.max_zoom];
	const source: string = anyLayer.source_type;
	// @ts-expect-error A vector tile layer has a source type, never field names.
	void anyLayer.field_names;
	void [zooms, source];
} else if (anyLayer.kind === "annotation") {
	const items: number = anyLayer.item_count;
	void items;
} else if (anyLayer.kind === "tiled_scene") {
	const box: { readonly x_min: number } = anyLayer.extent;
	void box;
} else {
	const fields: readonly string[] = anyLayer.field_names;
	void fields;
}
declare const rasterOnly: RasterLayerInfo;
// @ts-expect-error A raster layer carries bands, not fields.
void rasterOnly.field_names;
// @ts-expect-error A vector layer's geometry type is not a mesh's count.
void rasterOnly.vertex_count;

const geometry: VectorLayerInfo["geometry_type"] = "point";
void geometry;
// @ts-expect-error `surface` is not one of the declared geometry types.
const badGeometry: VectorLayerInfo["geometry_type"] = "surface";
void [wrongItems, badGeometry];
