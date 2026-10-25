import { BridgeClient } from "@archont561/qgis-sdk/bridge";
import { createApp } from "./app";
import { createOperations } from "./bridge";
import { connectWebChannel, insideQgis } from "./transport";

const root = document.querySelector<HTMLElement>("#app");
if (root === null) {
	throw new Error("index.html has no #app element");
}

if (insideQgis()) {
	connectWebChannel().then(
		(transport) =>
			createApp(root, createOperations(new BridgeClient(transport))),
		(failure: unknown) => {
			root.textContent =
				failure instanceof Error ? failure.message : String(failure);
		},
	);
} else {
	root.textContent =
		"Open this page from QGIS: outside a QGIS web view there is no host to talk to.";
}
