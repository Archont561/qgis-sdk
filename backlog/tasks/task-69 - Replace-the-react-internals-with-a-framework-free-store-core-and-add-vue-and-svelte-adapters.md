---
id: TASK-69
title: >-
  Replace the ./react internals with a framework-free store core and add ./vue
  and ./svelte adapters
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-26T09:06:00Z'
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
- [ ] #1 The four stores are typed end to end from the generated Operations/Streams and the host manifest, work against createBridgeHarness, and HostQueryStore exposes the refusal when the grant is absent; a behaviour test suite runs once against the core and once through each adapter and passes identically (bun tests).
- [ ] #2 ./react keeps its exported names and types (existing react.test.ts passes unchanged), ./vue and ./svelte exist as subpaths with optional peers, each with its own Vitest project; a consumer that imports only ./react has no vue or svelte in its bundle (build output check); typecheck, Biome and coverage are green.
- [ ] #3 The React and vanilla scaffold templates use the stores and Form/LayerPicker bindings in place of the bare button; the scaffold-web harness passes; doc-13 documents the stores, the three adapters, the vanilla path and the Tier 1 / Tier 2 table.
<!-- AC:END -->
