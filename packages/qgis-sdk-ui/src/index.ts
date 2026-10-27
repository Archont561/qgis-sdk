/**
 * `@archont561/qgis-sdk-ui`: the web half of the UI catalogue (decision-55),
 * as light-DOM custom elements on the store core of `@archont561/qgis-sdk`
 * (decision-47).
 *
 * Importing this module registers nothing; call {@link defineElements} once,
 * or import `@archont561/qgis-sdk-ui/define` for the side effect.
 */

export { type QgisChangeDetail, QgisSdkElement } from "./base";
export { StoreController } from "./controller";
export { type Choice, QgisChoice } from "./elements/choice";
export {
	AUTHID_PATTERN,
	COMMON_CRS,
	QgisCrsPicker,
} from "./elements/crs-picker";
export { QgisDistance } from "./elements/distance";
export { QgisFieldPicker } from "./elements/field-picker";
export {
	type FileRefPicker,
	QgisDirectoryInput,
	QgisFileInput,
} from "./elements/file-input";
export { type Pickers, QgisForm } from "./elements/form";
export {
	type Progress,
	type ProgressReader,
	type ProgressStatus,
	QgisJobProgress,
	readProgress,
} from "./elements/job-progress";
export { type AnyQgisSdk, QgisLayerPicker } from "./elements/layer-picker";
export { type LinesReader, QgisLogView, readLines } from "./elements/log-view";
export {
	type AnyFormStore,
	type AnyOperationStore,
	QgisRunButton,
} from "./elements/run-button";
export {
	applyTheme,
	clearTheme,
	DARK_TOKENS,
	LIGHT_TOKENS,
	PALETTE_ROLES,
	type QgisTheme,
	TOKEN_NAMES,
	type TokenName,
	type Tokens,
	tokenDeclarations,
	tokenProperty,
	tokensFromTheme,
	tokensStylesheet,
} from "./tokens";

import { QgisChoice } from "./elements/choice";
import { QgisCrsPicker } from "./elements/crs-picker";
import { QgisDistance } from "./elements/distance";
import { QgisFieldPicker } from "./elements/field-picker";
import { QgisDirectoryInput, QgisFileInput } from "./elements/file-input";
import { QgisForm } from "./elements/form";
import { QgisJobProgress } from "./elements/job-progress";
import { QgisLayerPicker } from "./elements/layer-picker";
import { QgisLogView } from "./elements/log-view";
import { QgisRunButton } from "./elements/run-button";

/** Every element of the catalogue, by tag name (decision-55). */
export const ELEMENTS: Readonly<Record<string, CustomElementConstructor>> =
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

/** The tag names, in catalogue order. */
export const TAG_NAMES: readonly string[] = Object.freeze(
	Object.keys(ELEMENTS),
);

/**
 * Register every element that is not registered yet. Safe to call twice;
 * a tag another script already took is left alone and reported.
 */
export function defineElements(
	registry: CustomElementRegistry = customElements,
): readonly string[] {
	const defined: string[] = [];
	for (const [tag, element] of Object.entries(ELEMENTS)) {
		if (registry.get(tag) === undefined) {
			registry.define(tag, element);
			defined.push(tag);
		}
	}
	return defined;
}
