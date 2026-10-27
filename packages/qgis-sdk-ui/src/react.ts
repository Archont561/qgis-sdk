/**
 * `@archont561/qgis-sdk-ui/react`: the catalogue as React components,
 * through `@lit/react`'s `createComponent` (task-70 AC #5).
 *
 * Each component forwards its props as element properties - `store`,
 * `qgis`, `value` and the rest keep their types - and maps the elements'
 * events to callbacks: `onQgisChange`, `onQgisResult`, `onQgisRun`,
 * `onQgisCancel`. Importing this module registers the elements where a
 * `customElements` registry exists; React 18 or later is the peer.
 */

import {
	createComponent,
	type EventName,
	type ReactWebComponent,
} from "@lit/react";
import * as React from "react";
import { QgisChoice as ChoiceElement } from "./elements/choice";
import { QgisCrsPicker as CrsPickerElement } from "./elements/crs-picker";
import { QgisDistance as DistanceElement } from "./elements/distance";
import { QgisFieldPicker as FieldPickerElement } from "./elements/field-picker";
import {
	QgisDirectoryInput as DirectoryInputElement,
	QgisFileInput as FileInputElement,
} from "./elements/file-input";
import { QgisForm as FormElement } from "./elements/form";
import { QgisJobProgress as JobProgressElement } from "./elements/job-progress";
import { QgisLayerPicker as LayerPickerElement } from "./elements/layer-picker";
import { QgisLogView as LogViewElement } from "./elements/log-view";
import { QgisRunButton as RunButtonElement } from "./elements/run-button";
import type {
	QgisCancelEvent,
	QgisChangeEvent,
	QgisResultEvent,
	QgisRunEvent,
} from "./events";
import { defineElements } from "./index";

export type {
	QgisCancelEvent,
	QgisChangeEvent,
	QgisResultEvent,
	QgisRunEvent,
} from "./events";

if (typeof customElements !== "undefined") {
	defineElements();
}

/** The callbacks of a control that reports a value. */
export type ChangeEvents = {
	readonly onQgisChange: EventName<QgisChangeEvent>;
};

/** The callbacks of a form or a run button. */
export type RunEvents = ChangeEvents & {
	readonly onQgisRun: EventName<QgisRunEvent>;
	readonly onQgisResult: EventName<QgisResultEvent>;
};

/** The callbacks of a progress bar. */
export type CancelEvents = {
	readonly onQgisCancel: EventName<QgisCancelEvent>;
};

const CHANGE: ChangeEvents = {
	onQgisChange: "qgis-change" as EventName<QgisChangeEvent>,
};
const RUN: RunEvents = {
	...CHANGE,
	onQgisRun: "qgis-run" as EventName<QgisRunEvent>,
	onQgisResult: "qgis-result" as EventName<QgisResultEvent>,
};
const CANCEL: CancelEvents = {
	onQgisCancel: "qgis-cancel" as EventName<QgisCancelEvent>,
};

function wrap<
	I extends HTMLElement,
	E extends Record<string, EventName | string>,
>(
	tagName: string,
	elementClass: new () => I,
	events: E,
): ReactWebComponent<I, E> {
	return createComponent({
		react: React,
		tagName,
		elementClass,
		events,
		displayName: elementClass.name,
	});
}

export const QgisForm: ReactWebComponent<FormElement, RunEvents> = wrap(
	"qgis-form",
	FormElement,
	RUN,
);
export const QgisLayerPicker: ReactWebComponent<
	LayerPickerElement,
	ChangeEvents
> = wrap("qgis-layer-picker", LayerPickerElement, CHANGE);
export const QgisCrsPicker: ReactWebComponent<CrsPickerElement, ChangeEvents> =
	wrap("qgis-crs-picker", CrsPickerElement, CHANGE);
export const QgisFieldPicker: ReactWebComponent<
	FieldPickerElement,
	ChangeEvents
> = wrap("qgis-field-picker", FieldPickerElement, CHANGE);
export const QgisJobProgress: ReactWebComponent<
	JobProgressElement,
	CancelEvents
> = wrap("qgis-job-progress", JobProgressElement, CANCEL);
export const QgisFileInput: ReactWebComponent<FileInputElement, ChangeEvents> =
	wrap("qgis-file-input", FileInputElement, CHANGE);
export const QgisDirectoryInput: ReactWebComponent<
	DirectoryInputElement,
	ChangeEvents
> = wrap("qgis-directory-input", DirectoryInputElement, CHANGE);
export const QgisDistance: ReactWebComponent<DistanceElement, ChangeEvents> =
	wrap("qgis-distance", DistanceElement, CHANGE);
export const QgisChoice: ReactWebComponent<ChoiceElement, ChangeEvents> = wrap(
	"qgis-choice",
	ChoiceElement,
	CHANGE,
);
export const QgisLogView: ReactWebComponent<
	LogViewElement,
	Record<never, never>
> = wrap("qgis-log-view", LogViewElement, {});
export const QgisRunButton: ReactWebComponent<RunButtonElement, RunEvents> =
	wrap("qgis-run-button", RunButtonElement, RUN);
