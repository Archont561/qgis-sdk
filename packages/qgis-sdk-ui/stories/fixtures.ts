/**
 * What the stories render against: the same fixture schema and harness
 * helpers the element tests use, so a story is a scripted host, never a
 * mock of the elements. Each story builds a fresh harness on every render;
 * `createBridgeHarness` answers what the story scripted and refuses the
 * rest by name.
 */

import type { HarnessOptions } from "@archont561/qgis-sdk/testing";
import {
	expectLayer,
	expectLayers,
	RIVERS,
	ROADS,
	schema,
	sdkWithHarness,
	type TestHarness,
	type TestSdk,
} from "../tests/support/schema";

export type { TestHarness, TestSdk };
export { expectLayer, expectLayers, RIVERS, ROADS, schema, sdkWithHarness };

/** A host that lists the fixture layers and describes `roads` on request. */
export function hostWithLayers(
	options: HarnessOptions = { granted: ["layers.list", "layers.get"] },
): { readonly harness: TestHarness; readonly qgis: TestSdk } {
	const { harness, qgis } = sdkWithHarness(options);
	expectLayers(harness);
	expectLayer(harness, ROADS);
	return { harness, qgis };
}

/** A host that granted nothing: every picker shows the refusal. */
export function hostWithoutGrants(): {
	readonly harness: TestHarness;
	readonly qgis: TestSdk;
} {
	return sdkWithHarness({ granted: [] });
}

/** A host-minted file reference, as `files.pick` would return one. */
export const PICKED = {
	kind: "file",
	id: "0123456789abcdef0123456789abcdef",
	name: "sites.gpkg",
	operations: ["read"],
} as const;
