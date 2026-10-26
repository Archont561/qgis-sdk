/**
 * The default transport: Qt's WebChannel, as a QGIS web view injects it.
 *
 * QGIS registers one object on the channel (the example names it "bridge";
 * see `create_channel_object` in the Python runtime). Its `receive` slot takes
 * a JSON envelope and its `message` signal carries every reply and stream
 * frame back. The channel becomes ready on a later turn, so this transport
 * is lazy: a `QgisSdk` built in the first statement of a page can send at
 * once, and what it sent is delivered when the channel reports ready.
 *
 * This is the one module of the root entry point that reads a browser global,
 * and it only does so when called: importing it touches nothing, and a page
 * that is not inside QGIS gets a synchronous, named refusal instead of a hang.
 */

import type { WireTransport } from "./bridge";
import { QgisSdkError } from "./errors";

interface ChannelObject {
	receive(text: string): void;
	readonly message: {
		connect(listener: (text: string) => void): void;
		disconnect(listener: (text: string) => void): void;
	};
}

interface Channel {
	readonly objects: Readonly<Record<string, ChannelObject | undefined>>;
}

interface QtScope {
	readonly qt?: { readonly webChannelTransport: unknown };
	readonly QWebChannel?: new (
		transport: unknown,
		ready: (channel: Channel) => void,
	) => unknown;
}

/** The web view did not provide a usable channel. */
export class QgisSdkWebChannelError extends QgisSdkError {
	public constructor(message: string) {
		super(message, "no_web_channel");
	}
}

/** The transport {@link createWebChannelTransport} returns. */
export interface WebChannelTransport extends WireTransport {
	/** Resolves once the channel object answered; rejects when it never will. */
	readonly ready: Promise<void>;
	/** Stop forwarding messages; sends after this throw. */
	close(): void;
}

function scope(): QtScope {
	return globalThis as unknown as QtScope;
}

/** True inside a QGIS web view, where Qt injected its transport and script. */
export function insideQgis(): boolean {
	const page = scope();
	return page.qt !== undefined && typeof page.QWebChannel === "function";
}

/**
 * Connect to the channel object `objectName` and return a transport on it.
 *
 * Throws {@link QgisSdkWebChannelError} synchronously outside a QGIS web view,
 * so a page learns in its first statement that it has no host to talk to.
 * Inside one, messages sent before the channel is ready are queued and
 * delivered in order once it is; `ready` rejects (and queued sends are
 * dropped) when the host registered no object under that name.
 */
export function createWebChannelTransport(
	objectName = "bridge",
): WebChannelTransport {
	const page = scope();
	const qt = page.qt;
	const QWebChannel = page.QWebChannel;
	if (qt === undefined || typeof QWebChannel !== "function") {
		throw new QgisSdkWebChannelError(
			"not inside a QGIS web view: window.qt is missing",
		);
	}
	const listeners = new Set<(message: unknown) => void>();
	const queue: string[] = [];
	let object: ChannelObject | null = null;
	let failure: QgisSdkWebChannelError | null = null;
	let closed = false;
	const forward = (text: string): void => {
		if (closed) {
			return;
		}
		let parsed: unknown;
		try {
			parsed = JSON.parse(text);
		} catch {
			return;
		}
		for (const listener of [...listeners]) {
			listener(parsed);
		}
	};
	const ready = new Promise<void>((resolve, reject) => {
		new QWebChannel(qt.webChannelTransport, (channel) => {
			const found = channel.objects[objectName];
			if (found === undefined) {
				failure = new QgisSdkWebChannelError(
					`the host registered no ${JSON.stringify(objectName)} channel object`,
				);
				queue.length = 0;
				reject(failure);
				return;
			}
			if (closed) {
				resolve();
				return;
			}
			object = found;
			found.message.connect(forward);
			for (const text of queue.splice(0)) {
				found.receive(text);
			}
			resolve();
		});
	});
	return {
		ready,
		send(message: unknown): void {
			if (closed) {
				throw new QgisSdkWebChannelError("the web channel transport is closed");
			}
			if (failure !== null) {
				throw failure;
			}
			const text = JSON.stringify(message);
			if (object === null) {
				queue.push(text);
				return;
			}
			object.receive(text);
		},
		subscribe(listener: (message: unknown) => void): () => void {
			listeners.add(listener);
			return () => {
				listeners.delete(listener);
			};
		},
		close(): void {
			if (closed) {
				return;
			}
			closed = true;
			queue.length = 0;
			listeners.clear();
			object?.message.disconnect(forward);
		},
	};
}
