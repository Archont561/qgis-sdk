---
id: TASK-70
title: >-
  Create @archont561/qgis-sdk-ui: web components on the store core, React, Vue
  and Svelte wrappers, palette tokens and Storybook
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-26T09:06:00Z'
labels: []
milestone: m-6
dependencies:
  - TASK-69
  - TASK-64
type: enhancement
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-47 points 3 and 5 (absorbing decision-46 points 4 and 5 and decision-16's theme half). New Bun workspace member packages/qgis-sdk-ui: web components qgis-form, qgis-layer-picker, qgis-crs-picker, qgis-field-picker, qgis-job-progress, qgis-file-input, qgis-directory-input, qgis-distance, qgis-choice, qgis-log-view, qgis-run-button (the decision-55 catalogue) built on the stores, Shadow-DOM scoped, styled through --qgis-sdk-* CSS variables; host() seeds the variables from the running QGIS palette when the page opens; wrappers at /react, /vue, /svelte add typed props and events only. Storybook (@storybook/web-components-vite) mounted on createBridgeHarness with scripted replies, faults and grant sets; portable stories are the Vitest fixtures; the static build publishes with the docs site (TASK-43). release.py gains the ui scope (ui-vX.Y.Z, stamp --scope ui, verify-versions checks the bridge peer range admits the workspace bridge); the gate runs the package with the bridge. Stories and Storybook config stay out of the tarball; scaffolded plugins do not get Storybook.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each component renders against createBridgeHarness through portable stories, the pickers show the refusal when the grant is absent, and the three wrappers pass the same behaviour suite in their own Vitest projects (bun tests).
- [ ] #2 Inside QGIS the page's --qgis-sdk-* variables match the running palette (webengine test reading computed styles) and fall back to documented defaults without a host; a Storybook theme switcher shows the QGIS light and dark palettes; bun run storybook serves and the static build lands in the docs site pipeline.
- [ ] #3 release.py stamp/verify-versions/plan know the ui scope and refuse a UI release whose bridge peer range excludes the workspace bridge (tests/scripts); npm pack of qgis-sdk-ui contains dist, README and LICENSE only; the Tier 1 templates opt in through one import and the scaffold-web harness passes.
- [ ] #4 decision-16 is promoted with a status review naming the palette tokens as the theme surface; doc-13 documents the components, wrappers and variables; the package README follows decision-29.
<!-- AC:END -->
