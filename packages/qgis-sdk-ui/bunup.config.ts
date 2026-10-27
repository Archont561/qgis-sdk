import { bunupPreset } from "@workspace/config/bunup";

export default {
	...bunupPreset,
	entry: [
		"src/index.ts",
		"src/define.ts",
		"src/uno.ts",
		"src/react.ts",
		"src/vue.ts",
		"src/svelte.ts",
	],
	// `lit` is the one dependency; the bridge is a peer the consumer already
	// has, each framework is its consumer's, and the UnoCSS preset is only
	// reached by a consumer that installed UnoCSS. Nothing else is bundled.
	external: [
		"lit",
		"@archont561/qgis-sdk",
		"@archont561/qgis-sdk/host",
		"@lit/react",
		"react",
		"vue",
		"svelte",
		"@unocss/preset-mini",
		"@unocss/core",
	],
	dts: { splitting: true },
};
