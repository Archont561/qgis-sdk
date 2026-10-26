/**
 * The default transport against a fake of what Qt injects (TASK-66 AC #3).
 *
 * `window.qt` and `window.QWebChannel` are stubbed on `globalThis` per test
 * and removed after it. This is mock evidence about queueing, delivery and
 * refusal; what a QWebEngineView does is covered by the Python qualification
 * harnesses (doc-14).
 */

import { test as base, expect } from "@archont561/bun-test-utils";
import { BridgeClient } from "../src/bridge";
import { QgisSdk } from "../src/qgis-sdk";
import {
	createWebChannelTransport,
	insideQgis,
	QgisSdkWebChannelError,
} from "../src/webchannel";
import schema from "./contracts/generated/clients/sites.schema";

interface FakeObject {
	readonly received: string[];
	readonly listeners: Set<(text: string) => void>;
	receive(text: string): void;
	readonly message: {
		connect(listener: (text: string) => void): void;
		disconnect(listener: (text: string) => void): void;
	};
}

interface FakeChannel {
	/** Call to let the channel report ready. */
	ready(): void;
	readonly objects: Record<string, FakeObject>;
}

const page = globalThis as Record<string, unknown>;

function fakeObject(): FakeObject {
	const listeners = new Set<(text: string) => void>();
	const received: string[] = [];
	return {
		received,
		listeners,
		receive: (text) => {
			received.push(text);
		},
		message: {
			connect: (listener) => listeners.add(listener),
			disconnect: (listener) => listeners.delete(listener),
		},
	};
}

/** Install the Qt globals; the channel reports ready only when told to. */
function install(objects: Record<string, FakeObject>): FakeChannel {
	let onReady:
		| ((channel: { objects: Record<string, FakeObject> }) => void)
		| null = null;
	page.qt = { webChannelTransport: {} };
	page.QWebChannel = class {
		public constructor(
			_transport: unknown,
			ready: (channel: { objects: Record<string, FakeObject> }) => void,
		) {
			onReady = ready;
		}
	};
	return {
		objects,
		ready: () => {
			onReady?.({ objects });
		},
	};
}

/** The Qt globals as a fixture: installed on demand, removed after the test. */
const test = base.extend({
	installQt: {
		setup: async (use) => {
			await use(install);
			delete page.qt;
			delete page.QWebChannel;
		},
	},
});

test("outside a QGIS web view the transport refuses synchronously and insideQgis is false", () => {
	expect(insideQgis()).toBe(false);
	expect(() => createWebChannelTransport()).toThrow(QgisSdkWebChannelError);
	try {
		createWebChannelTransport();
	} catch (error) {
		expect((error as QgisSdkWebChannelError).code).toBe("no_web_channel");
	}
});

test("messages sent before the channel is ready are delivered in order once it is", async ({
	installQt,
}) => {
	const bridge = fakeObject();
	const channel = installQt({ bridge });
	expect(insideQgis()).toBe(true);
	const transport = createWebChannelTransport();
	transport.send({ protocol: 1, call_id: "c1", kind: "handshake" });
	transport.send({ protocol: 1, call_id: "c2", operation: "x", payload: {} });
	expect(bridge.received).toEqual([]);
	channel.ready();
	await transport.ready;
	expect(bridge.received.map((text) => JSON.parse(text).call_id)).toEqual([
		"c1",
		"c2",
	]);
	transport.send({ protocol: 1, call_id: "c3" });
	expect(bridge.received).toHaveLength(3);
	transport.close();
});

test("replies from the channel object reach every subscriber, parsed", async ({
	installQt,
}) => {
	const bridge = fakeObject();
	const channel = installQt({ bridge });
	const transport = createWebChannelTransport();
	const seen: unknown[] = [];
	const detach = transport.subscribe((message) => seen.push(message));
	channel.ready();
	await transport.ready;
	expect(bridge.listeners.size).toBe(1);
	for (const listener of bridge.listeners) {
		listener(
			JSON.stringify({ protocol: 1, call_id: "c1", ok: true, value: 1 }),
		);
		listener("{not json");
	}
	expect(seen).toEqual([{ protocol: 1, call_id: "c1", ok: true, value: 1 }]);
	detach();
	for (const listener of bridge.listeners) {
		listener(
			JSON.stringify({ protocol: 1, call_id: "c2", ok: true, value: 2 }),
		);
	}
	expect(seen).toHaveLength(1);
	transport.close();
	expect(bridge.listeners.size).toBe(0);
	expect(() => transport.send({})).toThrow(QgisSdkWebChannelError);
});

test("a missing channel object rejects `ready`, drops the queue and fails later sends", async ({
	installQt,
}) => {
	const channel = installQt({});
	const transport = createWebChannelTransport("bridge");
	transport.send({ protocol: 1, call_id: "c1", kind: "handshake" });
	channel.ready();
	const failure = await transport.ready.then(
		() => null,
		(error: unknown) => error,
	);
	expect(failure).toBeInstanceOf(QgisSdkWebChannelError);
	expect((failure as Error).message).toContain('"bridge"');
	expect(() => transport.send({})).toThrow(QgisSdkWebChannelError);
});

test("the object name is configurable and the SDK uses it for its default transport", async ({
	installQt,
}) => {
	const panel = fakeObject();
	const channel = installQt({ panel });
	const qgis = QgisSdk.fromBridgeSchema(schema, { channelObject: "panel" });
	expect(qgis.client).toBeInstanceOf(BridgeClient);
	channel.ready();
	await Promise.resolve();
	// The handshake is the first thing a QgisSdk says.
	expect(panel.received.map((text) => JSON.parse(text).kind)).toEqual([
		"handshake",
	]);
	// Answer it the way the host would; `ready` resolves and `granted` fills.
	const callId = JSON.parse(panel.received[0] as string).call_id as string;
	for (const listener of panel.listeners) {
		listener(
			JSON.stringify({
				protocol: 1,
				call_id: callId,
				ok: true,
				value: {
					protocol: 1,
					generation: 0,
					plugin: null,
					host_schema_version: 1,
					operations: [{ id: "sites.summary" }, { id: "layers.get" }],
				},
			}),
		);
	}
	await qgis.ready;
	expect(qgis.host.granted).toEqual(["layers.get"]);
	qgis.close();
});

test("a three-statement page connects with no options at all", ({
	installQt,
}) => {
	const bridge = fakeObject();
	installQt({ bridge });
	const qgis = QgisSdk.fromBridgeSchema(schema);
	expect(typeof qgis["sites.summary"]).toBe("function");
	qgis.close();
});
