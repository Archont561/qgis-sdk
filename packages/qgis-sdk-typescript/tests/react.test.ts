/**
 * The thin React bindings (TASK-18 AC #1 and AC #2).
 *
 * Rendering happens in happy-dom, per test, through the `document` fixture;
 * React is driven with `act` so every effect and cleanup has run before an
 * assertion reads the harness. This is mock evidence about ownership and
 * leaks, not about a QWebEngineView.
 */

import { test as base, expect } from "@archont561/bun-test-utils";
import {
	act,
	createElement,
	type ReactElement,
	type ReactNode,
	StrictMode,
	useState,
} from "react";
import { createRoot, type Root } from "react-dom/client";
import { BridgeClient } from "../src/bridge";
import { QgisSdk } from "../src/qgis-sdk";
import {
	BridgeProvider,
	type OperationState,
	QgisSdkBridgeReactError,
	type StreamState,
	useBridgeClient,
	useOperation,
	useOperations,
	useQgisSdk,
	useStream,
} from "../src/react";
import {
	createBridgeHarness,
	fault,
	type ScriptedStream,
} from "../src/testing";
import {
	createOperations,
	type SitesSummaryResult,
	type SitesWatchEvent,
} from "./contracts/generated/clients/sites";
import schema, {
	type Operations,
	type Streams,
} from "./contracts/generated/clients/sites.schema";

type Op = "sites.summary" | "sites.watch";

interface Mounted {
	readonly container: HTMLElement;
	render(element: ReactElement): Promise<void>;
	unmount(): Promise<void>;
}

/** Run with React's console reporting of an expected render error muted. */
async function quietly(run: () => Promise<void>): Promise<void> {
	const original = console.error;
	console.error = () => {};
	try {
		await run();
	} finally {
		console.error = original;
	}
}

const test = base.extend({
	mount: {
		setup: async (use, { document }) => {
			(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
			const container = document.createElement("div");
			let root: Root | null = createRoot(container);
			const mounted: Mounted = {
				container,
				render: async (element) => {
					await act(async () => {
						root?.render(element);
					});
				},
				unmount: async () => {
					await act(async () => {
						root?.unmount();
					});
					root = null;
				},
			};
			await use(mounted);
			if (root !== null) {
				await act(async () => {
					root?.unmount();
				});
			}
		},
	},
});

function flush(): Promise<void> {
	return act(async () => {
		await new Promise((resolve) => setTimeout(resolve, 0));
	});
}

// -- ownership -----------------------------------------------------------------

function Probe({ seen }: { seen: BridgeClient[] }): ReactElement {
	seen.push(useBridgeClient());
	return createElement("i", null, "probe");
}

function Toggle({
	show,
	children,
}: {
	show: boolean;
	children?: ReactNode;
}): ReactElement | null {
	return show ? createElement("div", null, children) : null;
}

test("useBridgeClient outside a provider is a typed error, not undefined", async ({
	mount,
}) => {
	const seen: BridgeClient[] = [];
	await quietly(async () => {
		await expect(mount.render(createElement(Probe, { seen }))).rejects.toThrow(
			QgisSdkBridgeReactError,
		);
	});
	expect(seen).toEqual([]);
});

test("a provider needs exactly one of qgis, client or transport", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	const client = new BridgeClient(harness);
	const qgis = QgisSdk.fromBridgeSchema(schema, { client });
	await quietly(async () => {
		await expect(
			mount.render(createElement(BridgeProvider, {})),
		).rejects.toThrow(QgisSdkBridgeReactError);
		await expect(
			mount.render(
				createElement(BridgeProvider, { client, transport: harness }),
			),
		).rejects.toThrow(/exactly one/);
		await expect(
			mount.render(createElement(BridgeProvider, { qgis, client })),
		).rejects.toThrow(/exactly one/);
	});
	client.close();
});

// -- a QgisSdk instance (TASK-66 AC #3) ---------------------------------------

test("a provider given a QgisSdk shares it, its client, and never closes it", async ({
	mount,
}) => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const seenSdk: unknown[] = [];
	const seenClients: BridgeClient[] = [];
	function SdkProbe(): ReactElement {
		seenSdk.push(useQgisSdk<Operations, Streams>());
		seenClients.push(useBridgeClient());
		return createElement("i");
	}
	await mount.render(
		createElement(BridgeProvider, { qgis }, createElement(SdkProbe)),
	);
	expect(seenSdk).toEqual([qgis]);
	expect(seenClients).toEqual([qgis.client]);
	await mount.unmount();
	expect(qgis.client.isClosed).toBe(false);
	expect(harness.listeners).toBe(1);
	qgis.close();
	expect(harness.listeners).toBe(0);
});

test("useQgisSdk under a provider given only a client is a typed error", async ({
	mount,
}) => {
	const harness = createBridgeHarness(schema);
	const client = new BridgeClient(harness);
	function SdkProbe(): ReactElement {
		useQgisSdk();
		return createElement("i");
	}
	await quietly(async () => {
		await expect(
			mount.render(
				createElement(BridgeProvider, { client }, createElement(SdkProbe)),
			),
		).rejects.toThrow(/given a qgis instance/);
	});
	client.close();
});

test("useOperation and useStream take the methods of a QgisSdk as they are", async ({
	mount,
}) => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	harness.expectInvoke("sites.summary", (payload) => ({
		total: 2,
		largest: payload.layer_id,
		mode: "fast",
	}));
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("sites.watch", (_payload, s) => {
		stream = s;
	});
	const states: OperationState<SitesSummaryResult>[] = [];
	const streamStates: StreamState<SitesWatchEvent>[] = [];
	let run: ((input: { layer_id: string }) => Promise<unknown>) | null = null;
	function View(): ReactElement {
		const sdk = useQgisSdk<Operations, Streams>();
		const [state, start] = useOperation(sdk.sites.summary);
		states.push(state);
		run = start;
		streamStates.push(useStream(sdk.sites.watch, { layer_id: "sites" }));
		return createElement("i");
	}
	await mount.render(
		createElement(BridgeProvider, { qgis }, createElement(View)),
	);
	await flush();
	expect(streamStates.at(-1)?.status).toBe("open");
	await act(async () => {
		await run?.({ layer_id: "sites" });
		await harness.settled();
	});
	const last = states.at(-1);
	expect(last?.status === "ok" && last.value).toEqual({
		total: 2,
		largest: "sites",
		mode: "fast",
	});
	await act(async () => {
		stream?.emit("data", { change: "added", count: 2, layer_id: "sites" });
		await harness.settled();
	});
	expect(streamStates.at(-1)?.lastEvent).toEqual({
		kind: "data",
		payload: { change: "added", count: 2, layer_id: "sites" },
	});
	// A request outside the schema is the SDK's contract error, as state.
	await act(async () => {
		await run?.({ layer_id: 1 as never });
	});
	const refused = states.at(-1);
	expect(refused?.status === "error" && refused.error).toMatchObject({
		code: "contract_validation_failed",
	});
	await mount.unmount();
	await harness.settled();
	expect(harness.openSubscriptions).toEqual([]);
	harness.assertSatisfied();
	qgis.close();
});

test("a remounted child sees the same client and the transport keeps one listener", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	const seen: BridgeClient[] = [];
	const tree = (show: boolean): ReactElement =>
		createElement(
			BridgeProvider,
			{ transport: harness },
			createElement(Toggle, { show }, createElement(Probe, { seen })),
		);

	await mount.render(tree(true));
	await mount.render(tree(false));
	await mount.render(tree(true));

	expect(seen).toHaveLength(2);
	expect(seen[0]).toBe(seen[1] as BridgeClient);
	expect(harness.listeners).toBe(1);
});

test("a provider that owns its client closes it on unmount; an injected one is left alone", async ({
	mount,
	document,
}) => {
	const owned = createBridgeHarness<Op>();
	const seen: BridgeClient[] = [];
	await mount.render(
		createElement(
			BridgeProvider,
			{ transport: owned },
			createElement(Probe, { seen }),
		),
	);
	expect(owned.listeners).toBe(1);
	await mount.unmount();
	expect(owned.listeners).toBe(0);
	expect(seen[0]?.isClosed).toBe(true);

	const injectedHarness = createBridgeHarness<Op>();
	const injected = new BridgeClient(injectedHarness);
	const mount2 = createRoot(document.createElement("div"));
	await act(async () => {
		mount2.render(
			createElement(BridgeProvider, { client: injected }, createElement("b")),
		);
	});
	await act(async () => {
		mount2.unmount();
	});
	expect(injected.isClosed).toBe(false);
	expect(injectedHarness.listeners).toBe(1);
	injected.close();
});

test("under StrictMode an owned client survives the simulated remount", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () => ({
		total: 1,
		largest: "a",
		mode: "fast",
	}));
	const seen: BridgeClient[] = [];

	await mount.render(
		createElement(
			StrictMode,
			null,
			createElement(
				BridgeProvider,
				{ transport: harness },
				createElement(Probe, { seen }),
			),
		),
	);
	const live = seen.at(-1) as BridgeClient;
	expect(live.isClosed).toBe(false);
	expect(harness.listeners).toBe(1);
	await expect(
		live.invoke("sites.summary", { layer_id: "a" }),
	).resolves.toEqual({
		total: 1,
		largest: "a",
		mode: "fast",
	});
	await mount.unmount();
	expect(harness.listeners).toBe(0);
	harness.assertSatisfied();
});

// -- the same typed client, vanilla and React ---------------------------------

test("vanilla and React consume the same generated client over one transport", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () => ({
		total: 1,
		largest: "v",
		mode: "fast",
	}));
	harness.expectInvoke("sites.summary", () => ({
		total: 2,
		largest: "r",
		mode: "exact",
	}));
	const client = new BridgeClient(harness);
	const vanilla = await createOperations(client).sites.summary({
		layer_id: "sites",
	});

	let fromReact = null as SitesSummaryResult | null;
	let run: ((input: { layer_id: string }) => Promise<unknown>) | null = null;
	function View(): ReactElement {
		const operations = useOperations(createOperations);
		const [state, start] = useOperation(operations.sites.summary);
		run = start;
		if (state.status === "ok") {
			fromReact = state.value;
		}
		return createElement("i", { "data-status": state.status });
	}
	await mount.render(
		createElement(BridgeProvider, { client }, createElement(View)),
	);
	await act(async () => {
		await run?.({ layer_id: "sites" });
	});
	expect(mount.container.querySelector("i")?.getAttribute("data-status")).toBe(
		"ok",
	);

	expect(vanilla).toEqual({ total: 1, largest: "v", mode: "fast" });
	expect(fromReact).toEqual({ total: 2, largest: "r", mode: "exact" });
	expect(harness.calls.map((call) => call.callId)).toEqual(["c1", "c2"]);
	harness.assertSatisfied();
	client.close();
});

test("useOperations memoises per client, so a re-render does not rebuild the map", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	const maps: unknown[] = [];
	let rerender: (() => void) | null = null;
	function View(): ReactElement {
		const [, setTick] = useState(0);
		rerender = () => setTick((tick) => tick + 1);
		maps.push(useOperations(createOperations));
		return createElement("i");
	}
	await mount.render(
		createElement(BridgeProvider, { transport: harness }, createElement(View)),
	);
	await act(async () => {
		rerender?.();
	});
	expect(maps).toHaveLength(2);
	expect(maps[0]).toBe(maps[1]);
});

// -- useOperation -------------------------------------------------------------

test("useOperation moves idle -> pending -> ok, and a fault is an error with its code", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	// Each reply waits for the test to release it, so `pending` is observable
	// however fast the run is.
	const releases: (() => void)[] = [];
	const gated = <T>(reply: T): Promise<T> =>
		new Promise<T>((resolve) => {
			releases.push(() => resolve(reply));
		});
	harness.expectInvoke("sites.summary", () =>
		gated({ total: 1, largest: "a", mode: "fast" }),
	);
	harness.expectInvoke("sites.summary", () =>
		gated(fault("forbidden", "nope")),
	);
	const states: OperationState<SitesSummaryResult>[] = [];
	let run: ((input: { layer_id: string }) => Promise<unknown>) | null = null;
	function View(): ReactElement {
		const operations = useOperations(createOperations);
		const [state, start] = useOperation(operations.sites.summary);
		states.push(state);
		run = start;
		return createElement("i");
	}
	await mount.render(
		createElement(BridgeProvider, { transport: harness }, createElement(View)),
	);

	await act(async () => {
		void run?.({ layer_id: "a" });
	});
	expect(states.at(-1)?.status).toBe("pending");
	await act(async () => {
		releases.shift()?.();
		await harness.settled();
	});
	expect(states.at(-1)?.status).toBe("ok");
	await act(async () => {
		void run?.({ layer_id: "b" });
	});
	expect(states.at(-1)?.status).toBe("pending");
	await act(async () => {
		releases.shift()?.();
		await harness.settled();
	});

	expect(states.map((state) => state.status)).toEqual([
		"idle",
		"pending",
		"ok",
		"pending",
		"error",
	]);
	const last = states.at(-1);
	expect(last?.status === "error" && last.error).toMatchObject({
		code: "forbidden",
	});
	harness.assertSatisfied();
});

test("the latest run wins: a stale reply is ignored, and reset returns to idle", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	let releaseFirst: (() => void) | null = null;
	harness.expectInvoke("sites.summary", async () => {
		await new Promise<void>((resolve) => {
			releaseFirst = resolve;
		});
		return { total: 1, largest: "first", mode: "fast" };
	});
	harness.expectInvoke("sites.summary", () => ({
		total: 2,
		largest: "second",
		mode: "fast",
	}));
	let latest = null as OperationState<SitesSummaryResult> | null;
	let run: ((input: { layer_id: string }) => Promise<unknown>) | null = null;
	let reset: (() => void) | null = null;
	function View(): ReactElement {
		const operations = useOperations(createOperations);
		const [state, start, controls] = useOperation(operations.sites.summary);
		latest = state;
		run = start;
		reset = controls.reset;
		return createElement("i");
	}
	await mount.render(
		createElement(BridgeProvider, { transport: harness }, createElement(View)),
	);

	let first: Promise<unknown> | undefined;
	await act(async () => {
		first = run?.({ layer_id: "first" });
	});
	await act(async () => {
		await run?.({ layer_id: "second" });
	});
	expect(latest?.status === "ok" && latest.value.largest).toBe("second");
	await act(async () => {
		releaseFirst?.();
		await first;
	});
	expect(latest?.status === "ok" && latest.value.largest).toBe("second");

	await act(async () => {
		reset?.();
	});
	expect(latest?.status).toBe("idle");
	harness.assertSatisfied();
});

test("unmounting while a call is pending aborts it locally and settles nothing afterwards", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	let release = null as (() => void) | null;
	harness.expectInvoke("sites.summary", async () => {
		await new Promise<void>((resolve) => {
			release = resolve;
		});
		return { total: 1, largest: "a", mode: "fast" };
	});
	const states: string[] = [];
	let run: ((input: { layer_id: string }) => Promise<unknown>) | null = null;
	function View(): ReactElement {
		const operations = useOperations(createOperations);
		const [state, start] = useOperation(operations.sites.summary);
		states.push(state.status);
		run = start;
		return createElement("i");
	}
	await mount.render(
		createElement(BridgeProvider, { transport: harness }, createElement(View)),
	);
	let outcome: Promise<unknown> | undefined;
	await act(async () => {
		outcome = run?.({ layer_id: "a" });
	});
	await mount.unmount();
	await expect(outcome).resolves.toBeUndefined();
	release?.();
	await flush();

	expect(states).toEqual(["idle", "pending"]);
	harness.assertSatisfied();
});

// -- useStream ----------------------------------------------------------------

interface WatchProps {
	readonly layerId: string | null;
	readonly onEvent?: (event: SitesWatchEvent) => void;
	readonly states?: StreamState<SitesWatchEvent>[];
}

function Watch({ layerId, onEvent, states }: WatchProps): ReactElement {
	const operations = useOperations(createOperations);
	const state = useStream(
		operations.sites.watch,
		layerId === null ? null : { layer_id: layerId },
		{ onEvent },
	);
	states?.push(state);
	return createElement("i", { "data-status": state.status });
}

function provided(
	harness: ReturnType<typeof createBridgeHarness<Op>>,
	props: WatchProps | null,
): ReactElement {
	return createElement(
		BridgeProvider,
		{ transport: harness },
		props === null ? null : createElement(Watch, props),
	);
}

test("useStream opens on mount, delivers typed events to the latest handler, and closes on unmount", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("sites.watch", (_payload, s) => {
		stream = s;
	});
	const first: SitesWatchEvent[] = [];
	const second: SitesWatchEvent[] = [];
	const states: StreamState<SitesWatchEvent>[] = [];

	await mount.render(
		provided(harness, {
			layerId: "sites",
			onEvent: (e) => first.push(e),
			states,
		}),
	);
	await flush();
	expect(harness.openSubscriptions).toHaveLength(1);
	expect(states.at(-1)?.status).toBe("open");

	// A new handler identity must not reopen the stream.
	await mount.render(
		provided(harness, {
			layerId: "sites",
			onEvent: (e) => second.push(e),
			states,
		}),
	);
	await act(async () => {
		stream?.emit("data", { change: "added", count: 2, layer_id: "sites" });
		await harness.settled();
	});

	expect(first).toEqual([]);
	expect(second).toEqual([
		{ kind: "data", payload: { change: "added", count: 2, layer_id: "sites" } },
	]);
	expect(states.at(-1)?.lastEvent).toEqual(second[0] as SitesWatchEvent);
	expect(
		harness.calls.filter((call) => call.kind === "subscribe"),
	).toHaveLength(1);

	// Unmounting the component, not the provider: the client lives on, so the
	// host has to be told.
	await mount.render(provided(harness, null));
	await harness.settled();
	expect(harness.openSubscriptions).toEqual([]);
	expect(harness.calls.at(-1)?.kind).toBe("unsubscribe");
	harness.assertSatisfied();
});

test("unmounting the provider closes the client, which is how the host learns of every stream", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	harness.expectSubscribe("sites.watch", () => {});

	await mount.render(provided(harness, { layerId: "sites" }));
	await flush();
	expect(harness.openSubscriptions).toHaveLength(1);
	await mount.unmount();

	expect(harness.listeners).toBe(0);
	expect(harness.openSubscriptions).toEqual([]);
	// No unsubscribe envelope: the client closed first, and a closed client
	// sends nothing; the view going away is what disposes it host-side.
	expect(harness.calls.map((call) => call.kind)).toEqual(["subscribe"]);
	harness.assertSatisfied();
});

test("useStream reopens when the input changes and closes when it becomes null", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	const payloads: unknown[] = [];
	harness.expectSubscribe("sites.watch", (payload) => {
		payloads.push(payload);
	});
	harness.expectSubscribe("sites.watch", (payload) => {
		payloads.push(payload);
	});
	const states: StreamState<SitesWatchEvent>[] = [];

	await mount.render(provided(harness, { layerId: "a", states }));
	await flush();
	await mount.render(provided(harness, { layerId: "b", states }));
	await flush();
	expect(payloads).toEqual([{ layer_id: "a" }, { layer_id: "b" }]);
	expect(harness.openSubscriptions).toHaveLength(1);

	await mount.render(provided(harness, { layerId: null, states }));
	await flush();
	expect(harness.openSubscriptions).toEqual([]);
	expect(states.at(-1)?.status).toBe("idle");
	harness.assertSatisfied();
});

test("a host terminal ends the stream once and is visible as state", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("sites.watch", (_payload, s) => {
		stream = s;
	});
	const states: StreamState<SitesWatchEvent>[] = [];

	await mount.render(provided(harness, { layerId: "sites", states }));
	await flush();
	await act(async () => {
		stream?.end({ kind: "error", message: "layer vanished" });
		await harness.settled();
	});

	expect(states.at(-1)).toMatchObject({
		status: "ended",
		terminal: { kind: "error", message: "layer vanished" },
	});
	await mount.unmount();
	await harness.settled();
	expect(harness.calls.filter((call) => call.kind === "unsubscribe")).toEqual(
		[],
	);
	harness.assertSatisfied();
});

test("a refused subscription is a failed state carrying the remote code", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	harness.expectSubscribe("sites.watch", () => fault("forbidden", "no"));
	const states: StreamState<SitesWatchEvent>[] = [];

	await mount.render(provided(harness, { layerId: "sites", states }));
	await flush();

	expect(states.at(-1)?.status).toBe("failed");
	expect(states.at(-1)?.error).toMatchObject({ code: "forbidden" });
	harness.assertSatisfied();
});

test("under StrictMode the simulated remount leaves exactly one open subscription", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	harness.expectSubscribe("sites.watch", () => {});
	harness.expectSubscribe("sites.watch", () => {});

	await mount.render(
		createElement(StrictMode, null, provided(harness, { layerId: "sites" })),
	);
	await flush();
	await harness.settled();

	expect(harness.openSubscriptions).toHaveLength(1);
	await mount.unmount();
	await harness.settled();
	expect(harness.openSubscriptions).toEqual([]);
	// Both opens are accounted for: the first was closed by the simulated
	// unmount, the second by the real one.
	harness.assertSatisfied();
});

test("unmounting before the host acknowledges still closes the subscription", async ({
	mount,
}) => {
	const harness = createBridgeHarness<Op>();
	let ack: (() => void) | null = null;
	harness.expectSubscribe("sites.watch", () => {}, {
		ack: () =>
			new Promise<void>((resolve) => {
				ack = resolve;
			}),
	});

	await mount.render(provided(harness, { layerId: "sites" }));
	await mount.render(provided(harness, null));
	await act(async () => {
		ack?.();
		await harness.settled();
	});
	await flush();

	expect(harness.openSubscriptions).toEqual([]);
	expect(harness.calls.map((call) => call.kind)).toEqual([
		"subscribe",
		"unsubscribe",
	]);
	harness.assertSatisfied();
});
