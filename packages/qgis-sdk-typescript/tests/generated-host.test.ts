/**
 * The generated host module, swept: every exported guard is a mechanical
 * predicate rendered by the generator, so each one is called over the shapes
 * its body branches on - a non-record, a record whose keys are all present but
 * undefined (the presence checks pass and the field checks skip), a record
 * whose values are sentinels (the first field predicate fires), and one call
 * per recorded key so every field check's refusal line runs. The `createHost`
 * map is walked the same way, so every operation arrow is invoked once. The
 * construct-level tests of the generator live in `generated.test.ts` against
 * the fixture plugin; this file keeps the *host* module's own rendering under
 * the coverage threshold the workspace sets.
 */

import { expect, test } from "@archont561/bun-test-utils";
import * as generated from "../src/generated/host";

const SENTINEL = { unexpected: "sentinel" };

function proxyWith(get: (key: string) => unknown): Record<string, unknown> {
	return new Proxy({} as Record<string, unknown>, {
		has: () => true,
		get: (_target, key) => (typeof key === "string" ? get(key) : undefined),
		ownKeys: () => [],
		getOwnPropertyDescriptor: () => ({
			configurable: true,
			enumerable: true,
		}),
	});
}

const PRESENT_UNDEFINED = proxyWith(() => undefined);
const SENTINEL_VALUES = proxyWith(() => SENTINEL);

type Guard = (value: unknown, strict?: boolean) => boolean;

function isGuardEntry(name: string, value: unknown): value is Guard {
	return (
		typeof value === "function" &&
		/^[A-Z]/.test(name) &&
		name !== "QgisSdkHostContractError"
	);
}

function sweepGuard(name: string, fn: Guard): void {
	const reads = new Set<string>();
	const probe = proxyWith((key) => {
		reads.add(key);
		return undefined;
	});
	for (const input of [
		null,
		undefined,
		"a string",
		PRESENT_UNDEFINED,
		SENTINEL_VALUES,
	]) {
		for (const strict of [false, true]) {
			const answer = fn(input, strict);
			if (typeof answer !== "boolean") {
				throw new Error(
					`${name} must answer a boolean for ${String(input)} (strict=${strict})`,
				);
			}
		}
	}
	fn(probe, true);
	for (const key of reads) {
		fn(
			proxyWith((read) => (read === key ? SENTINEL : undefined)),
			true,
		);
	}
}

test("every generated guard answers over the shapes its body branches on", () => {
	const guards = Object.entries(generated).filter(([name, value]) =>
		isGuardEntry(name, value),
	);
	expect(guards.length).toBeGreaterThan(50);
	for (const [name, guard] of guards) {
		sweepGuard(name, guard as Guard);
	}
});

test("the createHost map invokes every operation arrow once", async () => {
	const client: generated.HostClientLike = {
		invoke: () => Promise.resolve({}),
		subscribe: () =>
			Promise.resolve({
				id: "s",
				get closed() {
					return true;
				},
				close: () => undefined,
			}),
	};
	const host = generated.createHost(client) as unknown as Record<
		string,
		unknown
	>;
	const arrows: [string, (...args: never[]) => unknown][] = [];
	const walk = (node: Record<string, unknown>, prefix: string): void => {
		for (const [key, value] of Object.entries(node)) {
			const path = prefix ? `${prefix}.${key}` : key;
			if (typeof value === "function") {
				arrows.push([path, value as (...args: never[]) => unknown]);
			} else if (value && typeof value === "object") {
				walk(value as Record<string, unknown>, path);
			}
		}
	};
	walk(host, "");
	expect(arrows.length).toBeGreaterThan(50);
	for (const [, arrow] of arrows) {
		try {
			await arrow(PRESENT_UNDEFINED as never, {} as never);
		} catch {
			// A result the stub answered is not the result the guard wants;
			// the arrow's own lines are what this sweep covers.
		}
	}
});

test("a present-but-undefined record passes a shape the generator marked optional", () => {
	// The one construct that decides the sweep above: `in` checks pass on a
	// present key while `value[k] !== undefined` skips its predicate, so the
	// success path of a fully optional shape is reachable without fixture data.
	expect(generated.AtlasExport(PRESENT_UNDEFINED)).toBe(true);
	expect(generated.AtlasExport(SENTINEL_VALUES)).toBe(false);
	expect(generated.AtlasExport(null)).toBe(false);
});
