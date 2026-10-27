/**
 * `@archont561/qgis-sdk-ui/uno`: the UnoCSS preset the package's own
 * `style.css` is compiled with, for a page that runs UnoCSS itself and wants
 * the catalogue's utilities and theme in its build instead of the stylesheet.
 *
 * Every utility is `qs-` prefixed and no preflight is emitted, so the preset
 * sits beside a consumer's Tailwind or Uno setup without a selector in
 * common (task-70 AC #5). The colours are the `--qgis-sdk-*` tokens, so a
 * `qs-bg-surface` follows the host palette like the stylesheet does.
 *
 * `@unocss/preset-mini` is an optional peer: only a page that imports this
 * entry needs it.
 */

import type { Preset } from "@unocss/core";
import { presetMini, type Theme } from "@unocss/preset-mini";
import { TOKEN_NAMES, type TokenName, tokenProperty } from "./tokens";

/** The classes the preset prefixes with. */
export const CLASS_PREFIX = "qs-";

/** The CSS variables preset-mini's own utilities use, kept out of `--un-*`. */
export const VARIABLE_PREFIX = "qs-";

const COLOUR_TOKENS: readonly TokenName[] = [
	"bg",
	"fg",
	"surface",
	"surface-fg",
	"control",
	"control-fg",
	"accent",
	"accent-fg",
	"border",
	"muted",
	"link",
	"danger",
];

/** The theme colours: one per colour token, each a `var(--qgis-sdk-*)`. */
export function tokenColours(): Readonly<Record<string, string>> {
	return Object.fromEntries(
		COLOUR_TOKENS.map((name) => [name, `var(${tokenProperty(name)})`]),
	);
}

/**
 * The preset: preset-mini, `qs-` prefixed, preflight-free, themed by the
 * tokens. The prefix is not an option: preset-mini writes it into rule
 * objects it shares across instances, so a process has one prefix, and the
 * elements' templates are written with `qs-`.
 */
export function presetQgisSdk(): Preset<Theme> {
	return {
		name: "@archont561/qgis-sdk-ui",
		prefix: CLASS_PREFIX,
		presets: [
			presetMini({
				prefix: CLASS_PREFIX,
				preflight: false,
				variablePrefix: VARIABLE_PREFIX,
			}),
		],
		// The nested preset's theme lands after this preset's own, so the
		// tokens are bound by extending the merged theme instead.
		extendTheme: (theme: Theme): void => {
			theme.colors = { ...theme.colors, ...tokenColours() };
			theme.fontFamily = {
				...theme.fontFamily,
				sans: `var(${tokenProperty("font")})`,
			};
			theme.borderRadius = {
				...theme.borderRadius,
				DEFAULT: `var(${tokenProperty("radius")})`,
			};
		},
		// preset-mini has no `accent-color` utility; the checkbox and the
		// progress bar want one, bound to a token like every other colour.
		rules: [
			[
				/^accent-([a-z-]+)$/,
				([, name]: RegExpMatchArray, { theme }: { theme: Theme }) => {
					const colour = (theme.colors as Record<string, unknown>)[
						name as string
					];
					return typeof colour === "string"
						? { "accent-color": colour }
						: undefined;
				},
			],
		],
	};
}

/** Every token the preset's theme reads, for a page listing what to set. */
export const PRESET_TOKENS: readonly TokenName[] = Object.freeze([
	...COLOUR_TOKENS,
	...TOKEN_NAMES.filter((name) => name === "font" || name === "radius"),
]);

export default presetQgisSdk;
