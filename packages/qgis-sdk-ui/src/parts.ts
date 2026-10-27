/**
 * The three parts every control is made of, rendered the same way everywhere.
 *
 * `data-part` is the hook a stylesheet or a test uses (task-70 AC #7); the
 * `qs-` classes are the package's own styling, compiled into `style.css`
 * and ignored by a page that brings its own.
 */

import { html, nothing, type TemplateResult } from "lit";

/** A label associated with the control `id`; nothing when `text` is empty. */
export function labelPart(
	id: string,
	text: string,
): TemplateResult | typeof nothing {
	return text === ""
		? nothing
		: html`<label data-part="label" class="qs-block qs-text-fg qs-mb-1" for=${id}>${text}</label>`;
}

/** An error paragraph under the control; nothing when `message` is empty. */
export function errorPart(
	id: string,
	message: string,
): TemplateResult | typeof nothing {
	return message === ""
		? nothing
		: html`<p data-part="error" class="qs-m-0 qs-mt-1 qs-text-danger" id=${id} role="alert">${message}</p>`;
}

/** The id a control's `aria-describedby` points at, or none. */
export function describedBy(id: string, message: string): string | undefined {
	return message === "" ? undefined : id;
}

/** Classes shared by every text-like control. */
export const CONTROL_CLASSES =
	"qs-box-border qs-w-full qs-rounded qs-border qs-border-border qs-bg-surface qs-text-surface-fg qs-px-2 qs-py-1 focus-visible:qs-outline-2 focus-visible:qs-outline-accent disabled:qs-opacity-60";

/** Classes shared by every button. */
export const BUTTON_CLASSES =
	"qs-rounded qs-border qs-border-border qs-bg-control qs-text-control-fg qs-px-3 qs-py-1 qs-cursor-pointer focus-visible:qs-outline-2 focus-visible:qs-outline-accent disabled:qs-opacity-60 disabled:qs-cursor-default";

/** Classes of a quiet status line. */
export const STATUS_CLASSES = "qs-m-0 qs-mt-1 qs-text-muted";
