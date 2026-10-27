/**
 * Progress, log and run button: what the host is doing, driven by
 * properties here and by stores in a page.
 */

import type { Meta, StoryObj } from "@storybook/web-components-vite";
import { html } from "lit";

interface ProgressArgs {
	readonly label: string;
	readonly status: "idle" | "pending" | "ok" | "error";
	readonly fraction: number | null;
	readonly message: string;
}

const meta: Meta<ProgressArgs> = {
	title: "Feedback/Job progress",
	args: {
		label: "Buffer",
		status: "pending",
		fraction: 0.4,
		message: "Reading features",
	},
	argTypes: {
		status: { control: "select", options: ["idle", "pending", "ok", "error"] },
		fraction: { control: { type: "range", min: 0, max: 1, step: 0.05 } },
	},
	render: (args) => html`<qgis-job-progress
		label=${args.label}
		status=${args.status}
		.fraction=${args.fraction}
		message=${args.message}
		.cancel=${args.status === "pending" ? () => undefined : null}
	></qgis-job-progress>`,
};

export default meta;
type Story = StoryObj<ProgressArgs>;

/** A running job with a known fraction and a cancel button. */
export const Pending: Story = {};

/** A job whose progress is unknown shows an indeterminate bar. */
export const Indeterminate: Story = {
	args: { fraction: null, message: "Working" },
};

/** Finished: the bar is full and the button is gone. */
export const Done: Story = { args: { status: "ok", fraction: 1, message: "" } };

/** Failed: the status is on the bar for the stylesheet to colour. */
export const Failed: Story = {
	args: {
		status: "error",
		fraction: null,
		message: "the layer is not writable",
	},
};

/** The log view: a live region of lines, trimmed to a limit, clearable. */
export const Log: Story = {
	render: () => html`<qgis-log-view
		label="Log"
		.lines=${["Opened roads", "Reprojected to EPSG:2180", "Buffered 1 204 features"]}
		.limit=${200}
		clearable
	></qgis-log-view>`,
};

/** The run button without a store is a plain button. */
export const RunButton: Story = {
	render: () =>
		html`<qgis-run-button label="Run" pending-label="Running…"></qgis-run-button>`,
};
