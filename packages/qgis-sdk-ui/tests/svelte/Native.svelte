<script>
// biome-ignore-all lint/correctness/noUnusedVariables: used in the template
// biome-ignore-all lint/correctness/noUnusedImports: used in the template
// Svelte's own property setting on a registered custom element: no action,
// the attributes become properties because the element has them.
let { qgis, value = null, onchange } = $props();
</script>

<qgis-layer-picker name="layer_id" label="Layer" {qgis} {value} onqgis-change={onchange}></qgis-layer-picker>
