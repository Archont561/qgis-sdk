import { QgisSdk } from "@archont561/qgis-sdk";
// The SDK's web components: this import registers every <qgis-*> element,
// the stylesheet styles them from the --qgis-sdk-* tokens applyHostTheme
// fills with the QGIS palette. Drop the three to go without.
import { applyHostTheme } from "@archont561/qgis-sdk-ui";
import "@archont561/qgis-sdk-ui/define";
import "@archont561/qgis-sdk-ui/style.css";
import { createApp } from "./app";
import schema from "./bridge.schema";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

// Three statements connect the page: import the generated schema, build the
// SDK on it, use it. Outside a QGIS web view the SDK refuses at once, with the
// reason, instead of waiting for a channel that will never come.
try {
	const qgis = QgisSdk.fromBridgeSchema(schema);
	void applyHostTheme(qgis);
	createApp(root, qgis);
} catch (failure: unknown) {
	root.textContent =
		failure instanceof Error
			? `${failure.message}. Open this page from QGIS: outside a QGIS web view there is no host to talk to.`
			: String(failure);
}
