/**
 * The `--qgis-sdk-*` theme surface: documented defaults, a host palette
 * mapped onto them, applied to and cleared from an element (task-70 AC #2,
 * decision-16).
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, uninstall } from "./support/dom";

install();
afterAll(uninstall);

const tokens = await import("../src/tokens");

describe("tokens", () => {
	test("every token has a light and a dark default, and a property name", () => {
		for (const name of tokens.TOKEN_NAMES) {
			expect(tokens.LIGHT_TOKENS[name]).not.toBe("");
			expect(tokens.DARK_TOKENS[name]).not.toBe("");
			expect(tokens.tokenProperty(name)).toBe(`--qgis-sdk-${name}`);
		}
		expect(tokens.LIGHT_TOKENS.bg).not.toBe(tokens.DARK_TOKENS.bg);
		expect(tokens.LIGHT_TOKENS.font).toBe(tokens.DARK_TOKENS.font);
	});

	test("a host palette fills the colour tokens over the matching defaults", () => {
		const light = tokens.tokensFromTheme({
			palette: {
				window: "#fafafa",
				highlight: "#ff00ff",
				unknownRole: "#000000",
				mid: "",
			},
		});
		expect(light.bg).toBe("#fafafa");
		expect(light.accent).toBe("#ff00ff");
		expect(light.border).toBe(tokens.LIGHT_TOKENS.border);
		expect(light.font).toBe(tokens.LIGHT_TOKENS.font);
		const dark = tokens.tokensFromTheme({
			palette: { windowText: "#eeeeee" },
			dark: true,
		});
		expect(dark.fg).toBe("#eeeeee");
		expect(dark.bg).toBe(tokens.DARK_TOKENS.bg);
		expect(Object.isFrozen(dark)).toBe(true);
		for (const role of Object.values(tokens.PALETTE_ROLES)) {
			expect(typeof role).toBe("string");
		}
	});

	test("applyTheme sets the properties on the root, clearTheme removes them", () => {
		const element = document.createElement("div");
		tokens.applyTheme(tokens.DARK_TOKENS, element);
		expect(element.style.getPropertyValue("--qgis-sdk-bg")).toBe(
			tokens.DARK_TOKENS.bg,
		);
		expect(element.style.getPropertyValue("--qgis-sdk-radius")).toBe(
			tokens.DARK_TOKENS.radius,
		);
		tokens.clearTheme(element);
		expect(element.style.getPropertyValue("--qgis-sdk-bg")).toBe("");

		tokens.applyTheme(tokens.LIGHT_TOKENS);
		expect(
			document.documentElement.style.getPropertyValue("--qgis-sdk-accent"),
		).toBe(tokens.LIGHT_TOKENS.accent);
		tokens.clearTheme();
		expect(
			document.documentElement.style.getPropertyValue("--qgis-sdk-accent"),
		).toBe("");
	});

	test("the stylesheet carries the light defaults on :root and the dark ones under the attribute", () => {
		const css = tokens.tokensStylesheet();
		expect(css.startsWith(":root {\n")).toBe(true);
		expect(css).toContain(`  --qgis-sdk-bg: ${tokens.LIGHT_TOKENS.bg};`);
		expect(css).toContain('[data-qgis-sdk-theme="dark"] {');
		expect(css).toContain(`  --qgis-sdk-bg: ${tokens.DARK_TOKENS.bg};`);
		expect(
			tokens.tokenDeclarations(tokens.LIGHT_TOKENS).split("\n"),
		).toHaveLength(tokens.TOKEN_NAMES.length);
	});
});
