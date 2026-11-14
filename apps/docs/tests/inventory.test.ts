/**
 * The inventory loader: the message a checkout without `api/python.json`
 * produces, and the document it accepts.
 *
 * `api/python.json` is committed and generated (decision-56), so the two ways a
 * build meets it are "somebody deleted it" and "somebody wrote half of it". The
 * loader exists to turn both into a sentence naming `qgis-sdk api dump`; a test
 * that only checked the happy path would let the JSON parser's own message back
 * in, which is the failure this module was written to replace.
 */
import { describe, expect, test } from "bun:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readInventory } from "../scripts/lib/inventory";

const ROOT = join(import.meta.dir, "../../..");

/** A throwaway directory, so nothing has to be created inside the checkout. */
async function scratch(): Promise<string> {
	return mkdtemp(join(tmpdir(), "qgis-sdk-inventory-"));
}

/** A file named like the inventory, holding `content`. */
async function inventoryHolding(content: string): Promise<string> {
	const path = join(await scratch(), "python.json");
	await writeFile(path, content, "utf8");
	return path;
}

describe("readInventory", () => {
	test("names the command that writes a missing inventory", async () => {
		const path = join(await scratch(), "python.json");
		// The path is asserted too: a bare "missing file" would be true of every
		// input the generator reads, and the reader has to know which one.
		await expect(readInventory(path)).rejects.toThrow(
			/no API inventory; run `qgis-sdk api dump`/,
		);
		await expect(readInventory(path)).rejects.toThrow(path);
	});

	test("reports a truncated document as not JSON, still naming the command", async () => {
		const path = await inventoryHolding('{ "api_version": 1, "modules": {');
		await expect(readInventory(path)).rejects.toThrow(/not JSON.*api dump/);
	});

	test("rejects a document that is JSON but not an inventory", async () => {
		// `api_version` alone is what a dump interrupted after the header leaves.
		const path = await inventoryHolding(JSON.stringify({ api_version: 1 }));
		await expect(readInventory(path)).rejects.toThrow(/not an API inventory/);
	});

	test("rejects a list where the document expects a list of objects", async () => {
		const path = await inventoryHolding(
			JSON.stringify({
				api_version: 1,
				modules: {},
				rules: {},
				cli: [],
				host_operations: [],
				deprecations: [],
			}),
		);
		await expect(readInventory(path)).rejects.toThrow(/not an API inventory/);
	});

	test("accepts the committed inventory", async () => {
		const document = await readInventory(join(ROOT, "api/python.json"));
		expect(document.api_version).toBe(1);
		expect(Object.keys(document.modules).length).toBeGreaterThan(0);
	});
});
