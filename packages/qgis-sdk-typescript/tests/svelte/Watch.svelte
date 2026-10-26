<script>
import { stream } from "../../src/svelte";

let { open, initial } = $props();
let layerId = $state(initial);
export function setLayer(id) {
	layerId = id;
}
const watch = stream(open);
$effect(() => {
	watch.setInput(layerId === null ? null : { layer_id: layerId });
});
</script>
<i>{$watch.status}</i>
