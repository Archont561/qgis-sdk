<script>
// biome-ignore-all lint/correctness/noUnusedImports: used in the template
// biome-ignore-all lint/correctness/noUnusedVariables: used in the template
import { setQgisSdk } from "../../src/svelte";
import Form from "./Form.svelte";

let { qgis, initial, onReady } = $props();
setQgisSdk(qgis);
</script>
<Form {initial} {onReady} />
