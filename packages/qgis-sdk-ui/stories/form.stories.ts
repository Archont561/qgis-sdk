/**
 * `qgis-form` over a `FormStore`: one control per declared field, in
 * declaration order, the catalogue's element for every kind that has one.
 * The focus order follows the declaration and ends on the run button.
 */

import { formStore } from "@archont561/qgis-sdk";
import type { Meta, StoryObj } from "@storybook/web-components-vite";
import { html } from "lit";
import { hostWithLayers, hostWithoutGrants } from "./fixtures";

interface FormArgs {
	readonly label: string;
	readonly submitLabel: string;
}

const meta: Meta<FormArgs> = {
	title: "Form",
	args: { label: "Buffer", submitLabel: "Run" },
	render: (args) => {
		const { qgis } = hostWithLayers();
		const store = formStore(qgis, "buffer");
		return html`<qgis-form
			label=${args.label}
			submit-label=${args.submitLabel}
			.store=${store}
			.qgis=${qgis}
		></qgis-form>`;
	},
};

export default meta;
type Story = StoryObj<FormArgs>;

/** Every field kind the fixture declares, with the layers granted. */
export const Buffer: Story = {};

/** The same form on a host that granted nothing: the pickers refuse. */
export const WithoutGrants: Story = {
	render: (args) => {
		const { qgis } = hostWithoutGrants();
		const store = formStore(qgis, "buffer");
		return html`<qgis-form
			label=${args.label}
			submit-label=${args.submitLabel}
			.store=${store}
			.qgis=${qgis}
		></qgis-form>`;
	},
};
