/**
 * The manager chrome follows the documentation site's theme.
 *
 * The published Storybook is served from `/storybook/` on the same origin as the
 * site, so it can read the preference Fumadocs stores (`localStorage.theme`,
 * `dark` or `light`, with `system` left to the OS). Without this the manager
 * follows `prefers-color-scheme` alone, and a reader who chose dark on a light
 * machine met a white frame around dark previews.
 *
 * `create({ base })` is Storybook's documented way to pick a base theme; it
 * recolours the chrome, not the canvas - `preview.ts` reads the same preference
 * for that.
 */

import { addons } from "storybook/manager-api";
import { create } from "storybook/theming";

export type ThemeName = "light" | "dark";

export function preferredTheme(): ThemeName {
	let stored: string | null = null;
	try {
		stored = localStorage.getItem("theme");
	} catch {
		// A storage-denied context falls through to the OS preference.
	}
	if (stored === "dark" || stored === "light") {
		return stored;
	}
	return window.matchMedia("(prefers-color-scheme: dark)").matches
		? "dark"
		: "light";
}

addons.setConfig({
	theme: create({
		base: preferredTheme(),
		brandTitle: "QGIS SDK",
	}),
});
