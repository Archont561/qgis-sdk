---
id: TASK-69
title: >-
  Replace the ./react internals with a framework-free store core and add ./vue
  and ./svelte adapters
status: Done
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-27 08:50'
labels: []
milestone: m-6
dependencies:
  - TASK-66
type: enhancement
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-47 points 1, 2 and 5 (amending decision-46 point 3). The bridge root exports typed stores - OperationStore, StreamStore, FormStore, HostQueryStore - built from the generated schema module (decision-44) and the host manifest, with the store contract getSnapshot/subscribe plus methods; ./react keeps its public API and re-implements it over the stores with useSyncExternalStore; new ./vue (composables, provide/inject, onScopeDispose) and ./svelte (store contract, runes wrapper, context) adapters as optional peers and separate build entries; the vanilla template uses the stores directly. Each adapter is tested in its own Vitest project against createBridgeHarness; no behaviour may live in an adapter. Ships in the bridge minor that m-6 releases.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The four stores are typed end to end from the generated Operations/Streams and the host manifest, work against createBridgeHarness, and HostQueryStore exposes the refusal when the grant is absent; a behaviour test suite runs once against the core and once through each adapter and passes identically (bun tests).
- [x] #2 ./react keeps its exported names and types (existing react.test.ts passes unchanged), ./vue and ./svelte exist as subpaths with optional peers, each with its own Vitest project; a consumer that imports only ./react has no vue or svelte in its bundle (build output check); typecheck, Biome and coverage are green.
- [x] #3 The React and vanilla scaffold templates use the stores and Form/LayerPicker bindings in place of the bare button; the scaffold-web harness passes; doc-13 documents the stores, the three adapters, the vanilla path and the Tier 1 / Tier 2 table.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Landed in one PR on `arena/efbb6cba-qgis-sdk` as three commits (69a `a2c653f` bridge + alias, 69b `3ddd7ca` scaffold, 69c docs + closure); see doc-19 for the slice table.

**Evidence per AC (pre-merge, this checkout):**
- AC #1: bridge `bun test` 301 pass / 0 fail across 15 files; `tests/store-behaviour.ts` (10 expectations) runs through `describeStoreBehaviour` with four drivers - core (`stores.test.ts`), React (`react-stores.test.ts`), Vue (`vue.test.ts`), Svelte (`svelte.test.ts` with mounted `tests/svelte/*.svelte` fixtures); `HostQueryStore` settles on `refused` without a call when `qgis.host.granted` lacks the operation (asserted in the suite and in both scaffold Vitest suites).
- AC #2: `react.test.ts` unchanged and green; `./vue` and `./svelte` exports with optional peers `vue >=3.5`, `svelte >=5`; `tests/surface.test.ts` bundles each adapter and pins that it reaches only its own framework; `bun run build` = `bunup && bun tests/consumer/isolation.ts && tsc -p tsconfig.dist.json` (the isolation script walks `dist/*.js` + chunks: 7 entries, each reaches its own framework only); `pixi run -e bun typecheck`, `pixi run biome-check` (83 files) and `bun run coverage` (stores/vue 100 %, react 100/99.2, svelte 100/98.4, threshold 0.9) green.
- AC #3: `scaffold/web.py` vanilla page = `formStore(qgis, "ping", …)` + `layersQuery(qgis)`, React page = `useForm` + `useHostQuery(useMemo(() => layersQuery(qgis), [qgis]))`; `QGIS_SDK_SCAFFOLD_WEB=1` harness 8/8 (bun + npm × vanilla + React: install, Vitest, tsc, Vite build, built page pinged inside headless QGIS); `test_scaffold_web.py` + `test_reference_example.py` + `test_scaffold.py` 78 passed; doc-13 gained "Stores: the framework-free core", "Vue bindings", "Svelte bindings", the "Which entry for which page" Tier 1 / Tier 2 table and an unreleased-minor migration note.

**Decisions taken in flight:** the scaffold and the example now declare `grants = ["layers.read"]` so the starter layer picker lists layers out of the box (the page still renders the `refused` hint when an author removes it); happy-dom does not submit a form on a submit-button click, so both templates submit from a `type="button"` click and keep the form's `submit` handler for the Enter key; the example page keeps its direct-call workflow (the Tier 1 "three statements" path stays documented) - adopting the stores there is left to TASK-70's component work. Known limits: `layerFieldsQuery` and the other kinds have no scaffold rendering yet (TASK-70); Vue/Svelte remain Tier 2 (TASK-72).

2026-10-27: merged in PR #104 as `c8cd119`; CI green on Linux, macOS and Windows; evidence per AC in the notes above. Closed by the sprint 3 branch.
<!-- SECTION:NOTES:END -->
