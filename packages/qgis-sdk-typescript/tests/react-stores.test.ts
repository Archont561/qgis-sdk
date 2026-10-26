/**
 * The behaviour suite through the React adapter, plus what only the adapter
 * adds: `useForm` and `useHostQuery` under a provider. `tests/react.test.ts`
 * is unchanged by TASK-69 and proves the hook surface kept its shape.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { Window } from "happy-dom";
import { act, createElement, type ReactElement, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QgisSdk } from "../src/qgis-sdk";
import {
	BridgeProvider,
	useForm,
	useHostQuery,
	useOperation,
	useQgisSdk,
	useStream,
} from "../src/react";
import {
	type FormState,
	type FormStore,
	type HostQueryState,
	layersQuery,
	type OperationState,
	type Store,
	type StreamState,
} from "../src/stores";
import { createBridgeHarness } from "../src/testing";
import {
	type Driver,
	describeStoreBehaviour,
	type FormOperations,
	formSchema,
} from "./store-behaviour";

(
	globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let window: Window;
const roots = new Set<Root>();
const DOM_GLOBALS = ["window", "document", "HTMLElement", "navigator"] as const;
const previous = new Map<string, unknown>();

const originalError = console.error;

beforeEach(() => {
	// Store updates reach React outside `act` on purpose: that is how a page
	// drives them. The warning is noise here; a failure still fails.
	console.error = (...args: unknown[]) => {
		if (typeof args[0] === "string" && args[0].includes("not wrapped in act")) {
			return;
		}
		originalError(...args);
	};
	window = new Window();
	const g = globalThis as Record<string, unknown>;
	const w = window as unknown as Record<string, unknown>;
	for (const name of DOM_GLOBALS) {
		previous.set(name, g[name]);
		g[name] = name === "window" ? window : w[name];
	}
});

afterEach(async () => {
	for (const root of roots) {
		await act(async () => {
			root.unmount();
		});
	}
	roots.clear();
	console.error = originalError;
	await window.happyDOM.close();
	// `bun test` runs every file in one process: a global `window` left behind
	// makes json-schema-ref-parser (contracts.test.ts) read `location.href`.
	const g = globalThis as Record<string, unknown>;
	for (const name of DOM_GLOBALS) {
		const before = previous.get(name);
		if (before === undefined) {
			delete g[name];
		} else {
			g[name] = before;
		}
	}
	previous.clear();
});

interface Mounted<P> {
	/** Render again with new props; resolves once React has committed. */
	render(props: P): Promise<void>;
	unmount(): Promise<void>;
}

async function mount<P extends object>(
	component: (props: P) => ReactElement | null,
	props: P,
): Promise<Mounted<P>> {
	const container = window.document.createElement("div");
	const root = createRoot(container as unknown as HTMLElement);
	roots.add(root);
	const mounted: Mounted<P> = {
		render: async (next) => {
			await act(async () => {
				root.render(createElement(component, next));
			});
		},
		unmount: async () => {
			await act(async () => {
				root.unmount();
			});
			roots.delete(root);
		},
	};
	await mounted.render(props);
	return mounted;
}

/** Collect each distinct snapshot a hook rendered. */
function recorder<T>(): { history: T[]; push(value: T): void; current(): T } {
	const history: T[] = [];
	return {
		history,
		push(value) {
			if (history.length === 0 || !Object.is(history.at(-1), value)) {
				history.push(value);
			}
		},
		current: () => history.at(-1) as T,
	};
}

const settle = (): Promise<void> =>
	act(async () => {
		await new Promise((resolve) => setTimeout(resolve, 0));
	});

const react: Driver = {
	async operation(operation) {
		type State = OperationState<unknown>;
		const seen = recorder<State>();
		let run: ((input: unknown) => Promise<unknown>) | null = null;
		let controls: { abort(): void; reset(): void } | null = null;
		function View(): null {
			const [state, start, c] = useOperation(operation);
			seen.push(state);
			run = start as (input: unknown) => Promise<unknown>;
			controls = c;
			return null;
		}
		const mounted = await mount(View, {});
		return {
			history: seen.history as never,
			current: seen.current as never,
			// Store updates land outside `act`; `settle` flushes the re-render.
			run: (input) => (run as (i: unknown) => Promise<never>)(input),
			abort: () => controls?.abort(),
			reset: () => controls?.reset(),
			dispose: () => mounted.unmount(),
		};
	},
	async stream(open, input, handlers = {}) {
		const seen = recorder<StreamState<unknown>>();
		type Props = { input: unknown; handlers: typeof handlers };
		function View(props: Props): null {
			seen.push(useStream(open, props.input as never, props.handlers));
			return null;
		}
		let current: Props = { input, handlers };
		const mounted = await mount(View, current);
		return {
			history: seen.history as never,
			current: seen.current as never,
			setInput: async (next) => {
				current = { ...current, input: next };
				await mounted.render(current);
			},
			setHandlers: async (next) => {
				current = { ...current, handlers: next };
				await mounted.render(current);
			},
			dispose: () => mounted.unmount(),
		};
	},
	async form(qgis, id, options) {
		const seen = recorder<FormState<unknown>>();
		let store: ReturnType<typeof useForm<FormOperations, "buffer">>[1] | null =
			null;
		function View(): null {
			const [state, s] = useForm(qgis, id, options);
			seen.push(state);
			store = s;
			return null;
		}
		const mounted = await mount(View, {});
		const bound = store as unknown as FormStore<object, unknown>;
		return {
			history: seen.history as never,
			current: seen.current as never,
			fields: bound.fields,
			set: async (name, value) => {
				bound.set(name, value);
				await settle();
			},
			submit: () => bound.submit() as Promise<never>,
			reset: async () => {
				bound.reset();
				await settle();
			},
			dispose: () => mounted.unmount(),
		};
	},
	async layers(qgis) {
		const seen = recorder<HostQueryState<unknown>>();
		const query = layersQuery(qgis);
		function View(): null {
			const [state] = useHostQuery(query, { auto: false });
			seen.push(state);
			return null;
		}
		const mounted = await mount(View, {});
		return {
			history: seen.history as never,
			current: seen.current as never,
			refresh: () => query.refresh(),
			dispose: () => mounted.unmount(),
		};
	},
	settle,
};

describeStoreBehaviour("react", react);

describe("react: what the adapter adds", () => {
	test("useForm under a provider renders the declared fields and submits through the shared QgisSdk", async () => {
		const harness = createBridgeHarness(formSchema);
		harness.expectInvoke("buffer", (payload) => ({ id: payload.layer_id }));
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const seen = recorder<FormState<{ id: string }>>();
		let submit: (() => Promise<unknown>) | null = null;
		function Form(): ReactElement {
			const sdk = useQgisSdk<FormOperations, Record<never, never>>();
			const [state, form] = useForm(sdk, "buffer", {
				initial: { layer_id: "roads", distance_metres: 2 },
			});
			seen.push(state);
			submit = form.submit;
			return createElement(
				"form",
				null,
				form.fields.map((field) =>
					createElement("label", { key: field.name }, field.label),
				),
			);
		}
		function Page(): ReactElement {
			return createElement(
				StrictMode,
				null,
				createElement(BridgeProvider, { qgis }, createElement(Form)),
			);
		}
		const mounted = await mount(Page, {});
		expect(seen.current().valid).toBe(true);
		await act(async () => {
			await expect(submit?.()).resolves.toEqual({ id: "roads" });
		});
		expect(seen.current().submission).toEqual({
			status: "ok",
			value: { id: "roads" },
		});
		harness.assertSatisfied();
		await mounted.unmount();
		qgis.close();
	});

	test("useHostQuery refreshes on mount by default and aborts on unmount", async () => {
		const harness = createBridgeHarness(formSchema, { granted: [] });
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const query = layersQuery(qgis);
		const seen = recorder<HostQueryState<unknown>>();
		function View(): null {
			seen.push(useHostQuery(query)[0]);
			return null;
		}
		const mounted = await mount(View, {});
		await settle();
		expect(seen.current()).toMatchObject({ status: "refused" });
		await mounted.unmount();
		qgis.close();
	});

	test("useStore-backed hooks read the same snapshot a vanilla subscriber sees", async () => {
		const harness = createBridgeHarness(formSchema);
		harness.expectInvoke("buffer", () => ({ id: "x" }));
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		let store: Store<FormState<{ id: string }>> | null = null;
		const rendered: FormState<{ id: string }>[] = [];
		function View(): null {
			const [state, form] = useForm(qgis, "buffer");
			store = form;
			rendered.push(state);
			return null;
		}
		const mounted = await mount(View, {});
		const vanilla: FormState<{ id: string }>[] = [];
		(store as unknown as Store<FormState<{ id: string }>>).subscribe((s) => {
			vanilla.push(s);
		});
		expect(vanilla[0]).toBe(rendered.at(-1) as FormState<{ id: string }>);
		await mounted.unmount();
		qgis.close();
	});
});
