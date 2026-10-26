<script>
// biome-ignore-all lint/correctness/noUnusedVariables: used in the template
import { form, getQgisSdk, toRune } from "../../src/svelte";

let { initial, onReady } = $props();
const qgis = getQgisSdk();
const buffer = form(qgis, "buffer", { initial });
const rune = toRune(buffer);
onReady?.({ qgis, buffer });
</script>
<form data-valid={$buffer.valid} data-rune-valid={rune.current.valid}>
	{#each buffer.fields as field (field.name)}
		<label for={field.name}>{field.label}</label>
	{/each}
	<output>{$buffer.submission.status}</output>
</form>
