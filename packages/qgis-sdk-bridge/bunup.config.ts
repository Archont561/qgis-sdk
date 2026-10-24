import { bunupPreset } from "@workspace/config/bunup";

export default {
	...bunupPreset,
	entry: [
		"src/index.ts",
		"src/bridge.ts",
		"src/host.ts",
		"src/react.ts",
		"src/testing.ts",
	],
	external: ["react"],
};
