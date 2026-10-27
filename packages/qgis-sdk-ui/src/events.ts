/**
 * The events the elements raise, named once for the three wrappers.
 *
 * Each is a bubbling, composed `CustomEvent`; `detail` is what the row says.
 */

import type { QgisChangeDetail } from "./base";

/** `qgis-change`: a control's value changed; `detail` names the field. */
export type QgisChangeEvent = CustomEvent<QgisChangeDetail>;
/** `qgis-result`: a run button's call succeeded; `detail` is the value. */
export type QgisResultEvent = CustomEvent<unknown>;
/** `qgis-run`: a run button was pressed; no detail. */
export type QgisRunEvent = CustomEvent<undefined>;
/** `qgis-cancel`: a progress bar's cancel button was pressed; no detail. */
export type QgisCancelEvent = CustomEvent<undefined>;

/** Event name by the wrapper prop a framework would spell it as. */
export const EVENT_NAMES = Object.freeze({
	change: "qgis-change",
	result: "qgis-result",
	run: "qgis-run",
	cancel: "qgis-cancel",
}) as Readonly<{
	change: "qgis-change";
	result: "qgis-result";
	run: "qgis-run";
	cancel: "qgis-cancel";
}>;

/** The props of every element a wrapper forwards as properties, by tag. */
export const ELEMENT_PROPS: Readonly<Record<string, readonly string[]>> =
	Object.freeze({
		"qgis-form": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"store",
			"qgis",
			"pickers",
			"submitLabel",
		],
		"qgis-layer-picker": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"qgis",
			"value",
			"geometry",
			"nullable",
			"placeholder",
		],
		"qgis-crs-picker": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"value",
			"suggestions",
			"placeholder",
		],
		"qgis-field-picker": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"qgis",
			"layer",
			"of",
			"value",
			"nullable",
			"placeholder",
		],
		"qgis-job-progress": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"status",
			"fraction",
			"message",
			"store",
			"read",
			"cancel",
			"cancellable",
		],
		"qgis-file-input": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"value",
			"pick",
			"filters",
			"placeholder",
		],
		"qgis-directory-input": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"value",
			"pick",
			"filters",
			"placeholder",
		],
		"qgis-distance": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"value",
			"unit",
			"min",
			"max",
			"step",
		],
		"qgis-choice": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"options",
			"choices",
			"value",
			"nullable",
			"placeholder",
		],
		"qgis-log-view": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"lines",
			"limit",
			"store",
			"read",
			"clearable",
		],
		"qgis-run-button": [
			"name",
			"label",
			"disabled",
			"required",
			"error",
			"form",
			"operation",
			"input",
			"pendingLabel",
			"text",
		],
	});
