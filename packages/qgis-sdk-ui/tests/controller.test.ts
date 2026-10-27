/**
 * `StoreController`: subscribes while connected, lets go when the element
 * leaves, and follows a swapped store (task-70, "StoreController joins
 * stores to Lit").
 */

import { afterAll, describe, expect, test } from "bun:test";
import { container, install, tick, uninstall } from "./support/dom";

install();
afterAll(uninstall);

const { LitElement, html } = await import("lit");
const { StoreController } = await import("../src/controller");

interface Snapshot {
	readonly n: number;
}

/** A hand-rolled store that counts its listeners. */
function counterStore(): {
	readonly store: {
		getSnapshot: () => Snapshot;
		subscribe: (listener: (s: Snapshot) => void) => () => void;
	};
	publish(n: number): void;
	readonly listeners: () => number;
} {
	let snapshot: Snapshot = { n: 0 };
	const listeners = new Set<(s: Snapshot) => void>();
	return {
		store: {
			getSnapshot: () => snapshot,
			subscribe(listener) {
				listeners.add(listener);
				listener(snapshot);
				return () => listeners.delete(listener);
			},
		},
		publish(n) {
			snapshot = { n };
			for (const listener of listeners) {
				listener(snapshot);
			}
		},
		listeners: () => listeners.size,
	};
}

class Probe extends LitElement {
	public readonly controller = new StoreController<Snapshot>(this);
	public renders = 0;
	protected override createRenderRoot(): HTMLElement {
		return this;
	}
	protected override render(): unknown {
		this.renders += 1;
		return html`<output>${this.controller.value?.n ?? "none"}</output>`;
	}
}
customElements.define("x-probe", Probe);

describe("StoreController", () => {
	test("renders the snapshot, re-renders on publish, unsubscribes on disconnect", async () => {
		const counter = counterStore();
		const root = container();
		const probe = document.createElement("x-probe") as Probe;
		probe.controller.store = counter.store;
		root.append(probe);
		await tick();
		expect(root.querySelector("output")?.textContent).toBe("0");
		expect(counter.listeners()).toBe(1);

		counter.publish(7);
		await tick();
		expect(root.querySelector("output")?.textContent).toBe("7");

		probe.remove();
		expect(counter.listeners()).toBe(0);
		root.append(probe);
		await tick();
		expect(counter.listeners()).toBe(1);
		probe.remove();
	});

	test("a swapped store is followed, the old one released; null follows nothing", async () => {
		const first = counterStore();
		const second = counterStore();
		const root = container();
		const probe = document.createElement("x-probe") as Probe;
		root.append(probe);
		await tick();
		expect(root.querySelector("output")?.textContent).toBe("none");

		probe.controller.store = first.store;
		await tick();
		expect(root.querySelector("output")?.textContent).toBe("0");
		second.publish(3);
		probe.controller.store = second.store;
		await tick();
		expect(first.listeners()).toBe(0);
		expect(second.listeners()).toBe(1);
		expect(root.querySelector("output")?.textContent).toBe("3");

		probe.controller.store = second.store;
		expect(second.listeners()).toBe(1);
		probe.controller.store = null;
		expect(second.listeners()).toBe(0);
		expect(probe.controller.value).toBeUndefined();
		expect(probe.controller.store).toBeNull();
		probe.remove();
	});
});
