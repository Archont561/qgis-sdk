/**
 * Import for the side effect: the catalogue registered with Polaris
 * rendering (decision-87).
 *
 * Load the vendored `polaris-2.js` bundle before this import. The elements
 * detect the `<s-*>` tags and render Polaris components; without the bundle
 * they render the native controls, exactly as `define` does.
 *
 * ```html
 * <script src="./polaris-2.js"></script>
 * <script type="module">
 *   import "@archont561/qgis-sdk-ui/polaris";
 * </script>
 * ```
 */

import { defineElements } from "./index";

export const DEFINED: readonly string[] = defineElements();
