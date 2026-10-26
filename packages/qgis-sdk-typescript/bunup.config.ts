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
	// One declaration per type across the five entry points. Without this each
	// `.d.ts` carries its own copy of `BridgeClient`, and a class with a private
	// member is nominal: a `QgisSdk` from the root was not assignable to the
	// `qgis` prop of `./react`, which the scaffold harness caught.
	dts: { splitting: true },
};
