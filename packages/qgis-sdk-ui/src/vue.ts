/**
 * `@archont561/qgis-sdk-ui/vue`: the catalogue as Vue 3 components.
 *
 * Each component forwards its props as element properties (`.prop`
 * bindings in the render function, so a `store` or a `qgis` crosses as an
 * object) and re-emits the elements' events as `change`, `result`, `run`
 * and `cancel` with the event's `detail`. Importing this module registers
 * the elements where a `customElements` registry exists; Vue 3.4 or later is
 * the peer. A page that configures `compilerOptions.isCustomElement` may use
 * the tags directly instead.
 */

import { type DefineComponent, defineComponent, h, type PropType } from "vue";
import { ELEMENT_PROPS, EVENT_NAMES } from "./events";
import { defineElements } from "./index";

if (typeof customElements !== "undefined") {
	defineElements();
}

/** The emits of every wrapped element, by the event they re-emit. */
export type WrapperEmits = {
	readonly change: (detail: {
		readonly name: string;
		readonly value: unknown;
	}) => void;
	readonly result: (detail: unknown) => void;
	readonly run: () => void;
	readonly cancel: () => void;
};

/** A wrapped element: its properties as optional props of any type. */
export type ElementComponent = DefineComponent<Record<string, unknown>>;

function wrap(tag: string): ElementComponent {
	const names = ELEMENT_PROPS[tag] ?? [];
	const props = Object.fromEntries(
		names.map((name) => [
			name,
			{ type: null as unknown as PropType<unknown>, default: undefined },
		]),
	);
	return defineComponent({
		name: tag
			.split("-")
			.map((part) => part.charAt(0).toUpperCase() + part.slice(1))
			.join(""),
		props,
		emits: ["change", "result", "run", "cancel"],
		setup(received, { emit, slots }) {
			return () => {
				const bound: Record<string, unknown> = {};
				for (const name of names) {
					const value = received[name];
					if (value !== undefined) {
						bound[`.${name}`] = value;
					}
				}
				bound[`on${capitalise(EVENT_NAMES.change)}`] = (event: CustomEvent) =>
					emit("change", event.detail);
				bound[`on${capitalise(EVENT_NAMES.result)}`] = (event: CustomEvent) =>
					emit("result", event.detail);
				bound[`on${capitalise(EVENT_NAMES.run)}`] = () => emit("run");
				bound[`on${capitalise(EVENT_NAMES.cancel)}`] = () => emit("cancel");
				return h(tag, bound, slots.default?.());
			};
		},
	}) as ElementComponent;
}

/** `qgis-change` -> `Qgis-change`: what Vue's `on` prefix wants for a hyphenated event. */
function capitalise(name: string): string {
	return name.charAt(0).toUpperCase() + name.slice(1);
}

export const QgisForm: ElementComponent = wrap("qgis-form");
export const QgisLayerPicker: ElementComponent = wrap("qgis-layer-picker");
export const QgisCrsPicker: ElementComponent = wrap("qgis-crs-picker");
export const QgisFieldPicker: ElementComponent = wrap("qgis-field-picker");
export const QgisJobProgress: ElementComponent = wrap("qgis-job-progress");
export const QgisFileInput: ElementComponent = wrap("qgis-file-input");
export const QgisDirectoryInput: ElementComponent = wrap(
	"qgis-directory-input",
);
export const QgisDistance: ElementComponent = wrap("qgis-distance");
export const QgisChoice: ElementComponent = wrap("qgis-choice");
export const QgisLogView: ElementComponent = wrap("qgis-log-view");
export const QgisRunButton: ElementComponent = wrap("qgis-run-button");

/** Every wrapped component by tag, for `app.component` registration in a loop. */
export const components: Readonly<Record<string, ElementComponent>> =
	Object.freeze({
		"qgis-form": QgisForm,
		"qgis-layer-picker": QgisLayerPicker,
		"qgis-crs-picker": QgisCrsPicker,
		"qgis-field-picker": QgisFieldPicker,
		"qgis-job-progress": QgisJobProgress,
		"qgis-file-input": QgisFileInput,
		"qgis-directory-input": QgisDirectoryInput,
		"qgis-distance": QgisDistance,
		"qgis-choice": QgisChoice,
		"qgis-log-view": QgisLogView,
		"qgis-run-button": QgisRunButton,
	});
