/**
 * The theme surface: `--qgis-sdk-*` custom properties (decision-16).
 *
 * Inside QGIS the host's palette fills them (`applyTheme` from the handshake's
 * `theme`); outside, `tokens.css` carries the defaults below, light by default
 * and dark under `[data-qgis-sdk-theme="dark"]`. Every colour utility of
 * `style.css` reads a token, never a literal, so a page restyles the whole
 * catalogue by setting the variables.
 */

/** The tokens, by the suffix of their custom property. */
export const TOKEN_NAMES = [
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
	"font",
	"font-size",
	"radius",
	"space",
] as const;

export type TokenName = (typeof TOKEN_NAMES)[number];

export type Tokens = Readonly<Record<TokenName, string>>;

/** The documented defaults for a page outside QGIS, or before the handshake. */
export const LIGHT_TOKENS: Tokens = Object.freeze({
	bg: "#efefef",
	fg: "#000000",
	surface: "#ffffff",
	"surface-fg": "#000000",
	control: "#efefef",
	"control-fg": "#000000",
	accent: "#3daee9",
	"accent-fg": "#ffffff",
	border: "#b9b9b9",
	muted: "#80808080",
	link: "#0000ff",
	danger: "#b3261e",
	font: "system-ui, sans-serif",
	"font-size": "13px",
	radius: "3px",
	space: "8px",
});

/** The dark counterpart: QGIS's "Night Mapping" palette, rounded. */
export const DARK_TOKENS: Tokens = Object.freeze({
	...LIGHT_TOKENS,
	bg: "#323232",
	fg: "#dddddd",
	surface: "#232629",
	"surface-fg": "#eff0f1",
	control: "#31363b",
	"control-fg": "#eff0f1",
	accent: "#3daee9",
	"accent-fg": "#eff0f1",
	border: "#5b5b5b",
	muted: "#a0a0a080",
	link: "#2980b9",
	danger: "#ff6b6b",
});

/** The custom property of a token. */
export function tokenProperty(name: TokenName): string {
	return `--qgis-sdk-${name}`;
}

/**
 * What the host sends about its palette: the `QPalette` colour roles the
 * WebEngine adapter reads from `QApplication.palette()`, as `#rrggbb` or
 * `#rrggbbaa`, plus whether the window colour is dark.
 */
export interface QgisTheme {
	readonly palette: Readonly<Record<string, string>>;
	readonly dark?: boolean;
}

/** Which palette role each colour token reads, when the host has it. */
export const PALETTE_ROLES: Readonly<Partial<Record<TokenName, string>>> =
	Object.freeze({
		bg: "window",
		fg: "windowText",
		surface: "base",
		"surface-fg": "text",
		control: "button",
		"control-fg": "buttonText",
		accent: "highlight",
		"accent-fg": "highlightedText",
		border: "mid",
		muted: "placeholderText",
		link: "link",
	});

/** The tokens a host palette produces: its roles over the matching defaults. */
export function tokensFromTheme(theme: QgisTheme): Tokens {
	const base = theme.dark === true ? DARK_TOKENS : LIGHT_TOKENS;
	const tokens: Record<TokenName, string> = { ...base };
	for (const [token, role] of Object.entries(PALETTE_ROLES) as [
		TokenName,
		string,
	][]) {
		const colour = theme.palette[role];
		if (typeof colour === "string" && colour !== "") {
			tokens[token] = colour;
		}
	}
	return Object.freeze(tokens);
}

/** Set every token as a custom property on `root` (the `<html>` element by default). */
export function applyTheme(
	tokens: Tokens,
	root: HTMLElement = document.documentElement,
): void {
	for (const name of TOKEN_NAMES) {
		root.style.setProperty(tokenProperty(name), tokens[name]);
	}
}

/** Remove every token from `root`, so the stylesheet defaults apply again. */
export function clearTheme(root: HTMLElement = document.documentElement): void {
	for (const name of TOKEN_NAMES) {
		root.style.removeProperty(tokenProperty(name));
	}
}

/** The CSS declarations of `tokens`, one per line, for a stylesheet. */
export function tokenDeclarations(tokens: Tokens): string {
	return TOKEN_NAMES.map(
		(name) => `  ${tokenProperty(name)}: ${tokens[name]};`,
	).join("\n");
}

/** The whole of `tokens.css`: light defaults on `:root`, dark under the attribute. */
export function tokensStylesheet(): string {
	return [
		":root {",
		tokenDeclarations(LIGHT_TOKENS),
		"}",
		'[data-qgis-sdk-theme="dark"] {',
		tokenDeclarations(DARK_TOKENS),
		"}",
		"",
	].join("\n");
}
