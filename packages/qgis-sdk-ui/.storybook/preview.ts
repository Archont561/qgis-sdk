/**
 * The project annotations every story runs under, in Storybook and in the
 * portable-story tests alike: a `theme` toolbar switching between the QGIS
 * light and dark palettes through the `--qgis-sdk-*` tokens (no rebuild, the
 * stylesheet only reads variables), the elements registered once, and the
 * a11y addon failing a story that violates a rule.
 */

import type { Preview } from "@storybook/web-components-vite";
import { html } from "lit";
import { defineElements } from "../src/index";
import { applyTheme, DARK_TOKENS, LIGHT_TOKENS } from "../src/tokens";

export type ThemeName = "light" | "dark";

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
	initialGlobals: { theme: "light" },
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
