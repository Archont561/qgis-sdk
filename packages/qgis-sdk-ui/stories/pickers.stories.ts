/**
 * The host-bound pickers: layers and fields through the grant-checking
 * queries. "Refused" is the page without `layers.read`; it is a state of
 * the component, not a broken story.
 */

import { fault } from "@archont561/qgis-sdk/testing";
import type { Meta, StoryObj } from "@storybook/web-components-vite";
import { html } from "lit";
import {
	hostWithLayers,
	hostWithoutGrants,
	ROADS,
	sdkWithHarness,
} from "./fixtures";

interface PickerArgs {
	readonly label: string;
	readonly nullable: boolean;
	readonly disabled: boolean;
}

const meta: Meta<PickerArgs> = {
	title: "Pickers/Layer",
	args: { label: "Layer", nullable: false, disabled: false },
	argTypes: {
		label: { control: "text" },
		nullable: { control: "boolean" },
		disabled: { control: "boolean" },
	},
	render: (args) => {
		const { qgis } = hostWithLayers();
		return html`<qgis-layer-picker
			name="layer_id"
			label=${args.label}
			?nullable=${args.nullable}
			?disabled=${args.disabled}
			.qgis=${qgis}
		></qgis-layer-picker>`;
	},
};

export default meta;
type Story = StoryObj<PickerArgs>;

/** The project's layers once `layers.read` is granted. */
export const Granted: Story = {};

/** A nullable picker keeps its empty option after a choice. */
export const Nullable: Story = { args: { nullable: true } };

/** Without the grant the picker says so and offers nothing. */
export const Refused: Story = {
	render: (args) => {
		const { qgis } = hostWithoutGrants();
		return html`<qgis-layer-picker
			name="layer_id"
			label=${args.label}
			.qgis=${qgis}
		></qgis-layer-picker>`;
	},
};

/** The host failed the call: the fault is shown next to the control. */
export const Faulted: Story = {
	render: (args) => {
		const { harness, qgis } = sdkWithHarness({ granted: ["layers.list"] });
		harness.expectInvoke("layers.list", () =>
			fault("internal_error", "the project is still loading"),
		);
		return html`<qgis-layer-picker
			name="layer_id"
			label=${args.label}
			.qgis=${qgis}
		></qgis-layer-picker>`;
	},
};

/** A field picker bound to a layer lists that layer's fields. */
export const FieldsOfALayer: Story = {
	args: { label: "Field" },
	render: (args) => {
		const { qgis } = hostWithLayers();
		return html`<qgis-field-picker
			name="field_name"
			label=${args.label}
			.layer=${ROADS.id}
			?nullable=${args.nullable}
			.qgis=${qgis}
		></qgis-field-picker>`;
	},
};

/** A field picker with no layer chosen yet waits, disabled. */
export const FieldsWithoutALayer: Story = {
	args: { label: "Field" },
	render: (args) => {
		const { qgis } = hostWithLayers();
		return html`<qgis-field-picker
			name="field_name"
			label=${args.label}
			.qgis=${qgis}
		></qgis-field-picker>`;
	},
};
