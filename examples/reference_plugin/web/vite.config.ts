import { defineConfig } from "vitest/config";

// QGIS shows the page in Qt WebEngine, which is Chromium: Qt 6.5's is
// Chromium 108. Raise the target together with qgisMinimumVersion, never
// above what the oldest QGIS you support ships.
export default defineConfig({
	base: "./",
	build: {
		outDir: "../reference_plugin/web",
		emptyOutDir: true,
		target: "chrome108",
	},
	test: {
		environment: "happy-dom",
	},
});
