import { bunupPreset } from "@workspace/config/bunup";

export default {
	...bunupPreset,
	entry: [
		"src/index.ts",
		"src/bridge.ts",
		"src/host.ts",
		"src/react.ts",
		"src/vue.ts",
		"src/svelte.ts",
		"src/testing.ts",
	],
	// Each adapter's framework is its consumer's; `tests/consumer/isolation.ts`
	// checks after every build that no entry pulled in another's.
	external: ["react", "vue", "svelte", "svelte/store"],
	// One declaration per type across the seven entry points. Without this each
	// `.d.ts` carries its own copy of `BridgeClient`, and a class with a private
	// member is nominal: a `QgisSdk` from the root was not assignable to the
	// `qgis` prop of `./react`, which the scaffold harness caught.
	dts: { splitting: true },
};
