/**
 * The stories as fixtures (task-70 AC #1, #2, #7): every story composes
 * under the preview's project annotations and renders in the test DOM;
 * each rendered element carries its `data-qgis-sdk` id and `data-part`
 * hooks, every label points at a control in the light DOM, the form's
 * focus order follows the declaration, the refusal stories show the
 * refusal, and the theme toolbar's two palettes land as tokens.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, tick, uninstall } from "./support/dom";

install();
afterAll(uninstall);

const { composeStories } = await import("storybook/preview-api");
const { render } = await import("lit");
const { container } = await import("./support/dom");
const preview = (await import("../.storybook/preview")).default;
const { applyNamedTheme } = await import("../.storybook/preview");
const { tokenProperty, LIGHT_TOKENS, DARK_TOKENS } = await import(
	"../src/tokens"
);
const modules = {
	form: await import("../stories/form.stories"),
	pickers: await import("../stories/pickers.stories"),
	inputs: await import("../stories/inputs.stories"),
	feedback: await import("../stories/feedback.stories"),
};

type Composed = ((args?: object) => unknown) & {
	readonly id: string;
	readonly storyName: string;
};

/** Every story of every module, composed under the preview annotations. */
function allStories(): readonly [string, Composed][] {
	const out: [string, Composed][] = [];
	for (const [file, module] of Object.entries(modules)) {
		const composed = composeStories(
			module as never,
			preview as never,
		) as Record<string, Composed>;
		for (const [name, story] of Object.entries(composed)) {
			out.push([`${file}/${name}`, story]);
		}
	}
	return out;
}

const STORIES = allStories();

/** Render one composed story and let the host replies land. */
async function mountStory(story: Composed): Promise<HTMLElement> {
	const root = container();
	render(story() as never, root);
	await tick();
	await new Promise((resolve) => setTimeout(resolve, 0));
	await tick();
	return root;
}

// Declaration order of the tab stops; a control disabled until its layer is
// chosen (the field picker) is still a stop in that order.
const FOCUSABLE =
	"input:not([type=hidden]), select, button, [tabindex]:not([tabindex='-1'])";

describe("the stories as fixtures", () => {
	test("every module composes and the catalogue is covered", () => {
		const names = STORIES.map(([name]) => name);
		expect(names.length).toBeGreaterThanOrEqual(20);
		expect(names).toContain("form/Buffer");
		expect(names).toContain("pickers/Refused");
		expect(names).toContain("feedback/Log");
		for (const [, story] of STORIES) {
			expect(story.id).toMatch(/^[a-z0-9-]+--[a-z0-9-]+$/);
		}
	});

	test.each(STORIES)(
		"%s renders light-DOM elements with their hooks",
		async (_name, story) => {
			const root = await mountStory(story);
			const elements = [
				...root.querySelectorAll<HTMLElement>("[data-qgis-sdk]"),
			];
			expect(elements.length).toBeGreaterThan(0);
			for (const element of elements) {
				expect(element.localName.startsWith("qgis-")).toBe(true);
				expect(element.shadowRoot).toBeNull();
				expect(element.querySelector("[data-part]")).not.toBeNull();
			}
			for (const label of root.querySelectorAll<HTMLLabelElement>(
				"label[for]",
			)) {
				const control = root.querySelector(`#${label.htmlFor}`);
				expect(control).not.toBeNull();
				expect(["input", "select", "button", "textarea"]).toContain(
					control?.localName ?? "",
				);
			}
			// The theme decorator wrapped the story and put a palette on the root.
			expect(root.querySelector("[data-story-theme='light']")).not.toBeNull();
			expect(document.documentElement.getAttribute("data-qgis-sdk-theme")).toBe(
				"light",
			);
		},
	);

	test("the form story's focus order follows the declaration and ends on the run button", async () => {
		const [, buffer] = STORIES.find(([name]) => name === "form/Buffer") as [
			string,
			Composed,
		];
		const root = await mountStory(buffer);
		const fields = [...root.querySelectorAll<HTMLElement>("[data-field]")].map(
			(field) => field.dataset.field ?? "",
		);
		expect(fields.length).toBe(11);
		const focusable = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)];
		const seen: string[] = [];
		for (const element of focusable) {
			const field = element.closest<HTMLElement>("[data-field]")?.dataset.field;
			if (field !== undefined && seen.at(-1) !== field) {
				seen.push(field);
			}
		}
		expect(seen).toEqual(fields);
		expect(focusable.at(-1)?.localName).toBe("button");
		expect(focusable.at(-1)?.closest("qgis-run-button")).not.toBeNull();
	});

	test("the refusal stories show the refusal instead of a fault", async () => {
		for (const name of ["pickers/Refused", "form/WithoutGrants"]) {
			const [, story] = STORIES.find(([n]) => n === name) as [string, Composed];
			const root = await mountStory(story);
			const picker = root.querySelector<HTMLElement>("qgis-layer-picker");
			expect(picker?.textContent).toContain("layers.read");
			expect(picker?.querySelector("select")?.disabled).toBe(true);
		}
		const [, faulted] = STORIES.find(([n]) => n === "pickers/Faulted") as [
			string,
			Composed,
		];
		const root = await mountStory(faulted);
		expect(root.querySelector("[data-part='error']")?.textContent).toContain(
			"still loading",
		);
	});

	test("the theme toolbar switches the palette through the tokens, no rebuild", () => {
		const html = document.documentElement;
		applyNamedTheme("dark");
		expect(html.getAttribute("data-qgis-sdk-theme")).toBe("dark");
		expect(html.style.getPropertyValue(tokenProperty("bg"))).toBe(
			DARK_TOKENS.bg,
		);
		applyNamedTheme("light");
		expect(html.style.getPropertyValue(tokenProperty("bg"))).toBe(
			LIGHT_TOKENS.bg,
		);
		expect(preview.globalTypes?.theme?.toolbar?.items).toEqual([
			{ value: "light", title: "QGIS light" },
			{ value: "dark", title: "QGIS dark" },
		]);
		expect(preview.parameters?.a11y).toEqual({ test: "error" });
	});
});
