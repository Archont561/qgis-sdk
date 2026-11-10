/**
 * The project annotations every story runs under, in Storybook and in the
 * portable-story tests alike: a `theme` toolbar switching between the QGIS
 * light and dark palettes through the `--qgis-sdk-*` tokens (no rebuild, the
 * stylesheet only reads variables), the elements registered once, and the
 * a11y addon failing a story that violates a rule.
 *
 * The initial palette is the documentation site's choice, not a hard-coded
 * light: the published build is served from the site's origin, so the theme
 * Fumadocs stores is readable here, and a dark site opens dark previews. The
 * toolbar still wins once a reader picks a side. The preference is read when the
 * preview loads: a toggle in the site after the preview is open takes effect on
 * the next load, because Storybook's preview API exposes no globals setter here.
 */

import type { Preview } from "@storybook/web-components-vite";
import { html } from "lit";
import { defineElements } from "../src/index";
import { applyTheme, DARK_TOKENS, LIGHT_TOKENS } from "../src/tokens";

export type ThemeName = "light" | "dark";

/** The palette the documentation site is in, or the OS preference behind it. */
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

/** Put one palette on `root`, the way `applyHostTheme` does inside QGIS. */
export function applyNamedTheme(
	theme: ThemeName,
	root: HTMLElement = document.documentElement,
): void {
	applyTheme(theme === "dark" ? DARK_TOKENS : LIGHT_TOKENS, root);
	root.setAttribute("data-qgis-sdk-theme", theme);
}

defineElements();

const preview: Preview = {
	globalTypes: {
		theme: {
			description: "The QGIS palette the page runs under",
			toolbar: {
				title: "Theme",
				icon: "paintbrush",
				items: [
					{ value: "light", title: "QGIS light" },
					{ value: "dark", title: "QGIS dark" },
				],
				dynamicTitle: true,
			},
		},
	},
	initialGlobals: { theme: preferredTheme() },
	parameters: {
		a11y: { test: "error" },
		layout: "padded",
	},
	decorators: [
		(story, context) => {
			const theme = context.globals.theme === "dark" ? "dark" : "light";
			applyNamedTheme(theme);
			return html`<div data-story-theme=${theme} class="qs-text-fg">${story()}</div>`;
		},
	],
};

export default preview;
