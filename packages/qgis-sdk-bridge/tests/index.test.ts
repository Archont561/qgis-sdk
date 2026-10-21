import { expect, test } from "@archont561/bun-test-utils";
import * as entry from "@";
import * as source from "@/src";

test("the bridge entry point exposes no public API yet", () => {
	expect(Object.keys(entry)).toEqual([]);
});

test("the bare @ alias and @/src both resolve the bridge entry point", () => {
	expect(Object.keys(source)).toEqual([]);
	expect(entry).toBe(source);
});
