/**
 * The wire between this page and the plugin: Qt's WebChannel, nothing else.
 *
 * QGIS registers one object named "bridge" on the channel (see webview.py). Its
 * `receive` slot takes a JSON envelope; its `message` signal carries every
 * reply and stream frame back. Vitest never sees this file: the tests hand the
 * same client a scripted host from `@archont561/qgis-sdk/testing` instead.
 */

import type { WireTransport } from "@archont561/qgis-sdk/bridge";

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

declare global {
	interface Window {
		qt?: { readonly webChannelTransport: unknown };
		QWebChannel?: new (
			transport: unknown,
			ready: (channel: Channel) => void,
		) => unknown;
	}
}

/** True inside a QGIS web view, where Qt injected its transport and script. */
export function insideQgis(): boolean {
	return (
		typeof window !== "undefined" &&
		window.qt !== undefined &&
		typeof window.QWebChannel === "function"
	);
}

/** Resolve a transport once the channel is ready; reject outside QGIS. */
export function connectWebChannel(
	objectName = "bridge",
): Promise<WireTransport> {
	return new Promise((resolve, reject) => {
		if (
			!insideQgis() ||
			window.qt === undefined ||
			window.QWebChannel === undefined
		) {
			reject(new Error("not inside a QGIS web view: window.qt is missing"));
			return;
		}
		new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
			const object = channel.objects[objectName];
			if (object === undefined) {
				reject(
					new Error(`the host registered no "${objectName}" channel object`),
				);
				return;
			}
			resolve({
				send: (message) => object.receive(JSON.stringify(message)),
				subscribe: (listener) => {
					const forward = (text: string) => listener(JSON.parse(text));
					object.message.connect(forward);
					return () => object.message.disconnect(forward);
				},
			});
		});
	});
}
