/**
 * The host-free inputs: a distance with its unit, a typed choice, a CRS
 * with suggestions, and the file and directory inputs over a picker the
 * page supplies (inside QGIS, `files.pick`).
 */

import type { Meta, StoryObj } from "@storybook/web-components-vite";
import { html } from "lit";
import { PICKED } from "./fixtures";

interface InputArgs {
	readonly label: string;
	readonly error: string;
	readonly disabled: boolean;
}

const meta: Meta<InputArgs> = {
	title: "Inputs",
	args: { label: "Distance", error: "", disabled: false },
	argTypes: {
		label: { control: "text" },
		error: { control: "text" },
		disabled: { control: "boolean" },
	},
	render: (args) => html`<qgis-distance
		name="distance_metres"
		label=${args.label}
		unit="m"
		.min=${0}
		.value=${250}
		error=${args.error}
		?disabled=${args.disabled}
	></qgis-distance>`,
};

export default meta;
type Story = StoryObj<InputArgs>;

/** A distance in metres, bounded below at zero. */
export const Distance: Story = {};

/** A form's error renders as `data-part="error"`, described by the control. */
export const DistanceWithError: Story = {
	args: { error: "must be greater than 0" },
};

/** A choice keeps the type of its values: numbers stay numbers. */
export const Choice: Story = {
	args: { label: "Mode" },
	render: (args) => html`<qgis-choice
		name="mode"
		label=${args.label}
		.choices=${[
			{ value: "fast", label: "Fast" },
			{ value: "exact", label: "Exact" },
		]}
		.value=${"fast"}
		error=${args.error}
		?disabled=${args.disabled}
	></qgis-choice>`,
};

/** A CRS as `AUTHORITY:CODE`, with suggestions in a datalist. */
export const Crs: Story = {
	args: { label: "Working CRS" },
	render: (args) => html`<qgis-crs-picker
		name="crs"
		label=${args.label}
		.suggestions=${["EPSG:2180", "EPSG:3857", "EPSG:4326"]}
		.value=${"EPSG:2180"}
		error=${args.error}
		?disabled=${args.disabled}
	></qgis-crs-picker>`,
};

/** A file input over a picker: the reference is shown by name, never a path. */
export const File: Story = {
	args: { label: "Output" },
	render: (args) => html`<qgis-file-input
		name="output"
		label=${args.label}
		.filters=${["*.gpkg"]}
		.pick=${async () => PICKED}
		.value=${PICKED}
		error=${args.error}
		?disabled=${args.disabled}
	></qgis-file-input>`,
};

/** Without a picker the button is disabled and says why. */
export const FileWithoutAPicker: Story = {
	args: { label: "Output" },
	render: (args) => html`<qgis-file-input
		name="output"
		label=${args.label}
		error=${args.error}
	></qgis-file-input>`,
};

/** The directory flavour of the same element. */
export const Directory: Story = {
	args: { label: "Folder" },
	render: (args) => html`<qgis-directory-input
		name="folder"
		label=${args.label}
		.pick=${async () => ({ ...PICKED, kind: "directory" as const, name: "exports" })}
		error=${args.error}
		?disabled=${args.disabled}
	></qgis-directory-input>`,
};
