import { expect, test } from "@archont561/bun-test-utils";
import { hello as entryHello } from "@";
import { hello } from "@/src";

test("hello returns hello world", () => {
	expect(hello()).toBe("hello world");
});

test("bare @ alias resolves the bridge entry point", () => {
	expect(entryHello()).toBe("hello world");
});
