<script>
// biome-ignore-all lint/correctness/noUnusedVariables: used in the template
// biome-ignore-all lint/correctness/noUnusedImports: used in the template
// One element of the catalogue by tag, with the props the driver passes and
// the four listeners the wrappers name; `use:qgisProps` assigns the props.
// `update` is exported on the instance, so the driver can re-render.
import { ON, qgisProps } from "../../src/svelte";

let { tag, props, on = {} } = $props();
let current = $state({ ...props });
export function update(next) {
	current = { ...current, ...next };
}
const listeners = {
	[ON.change]: (event) => on.change?.(event.detail),
	[ON.result]: (event) => on.result?.(event.detail),
	[ON.run]: () => on.run?.(),
	[ON.cancel]: () => on.cancel?.(),
};
</script>

<svelte:element this={tag} use:qgisProps={current} {...listeners}></svelte:element>
