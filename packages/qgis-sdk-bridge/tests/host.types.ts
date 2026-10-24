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
// @ts-expect-error A page's items are VectorLayerInfo, never a loose record.
const wrongItems: Promise<readonly string[]> = page;

const geometry: VectorLayerInfo["geometry_type"] = "point";
void geometry;
// @ts-expect-error `surface` is not one of the declared geometry types.
const badGeometry: VectorLayerInfo["geometry_type"] = "surface";
void [wrongItems, badGeometry];
