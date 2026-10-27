---
id: TASK-70
title: >-
  Create @archont561/qgis-sdk-ui: web components on the store core, React, Vue
  and Svelte wrappers, palette tokens and Storybook
status: Done
assignee: []
created_date: '2026-10-26T08:52:00Z'
updated_date: '2026-10-27 14:10'
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
- [x] #1 Each component renders against createBridgeHarness through portable stories, the pickers show the refusal when the grant is absent, and the three wrappers pass the same behaviour suite in their own Vitest projects (bun tests).
- [x] #2 Inside QGIS the page's --qgis-sdk-* variables match the running palette (webengine test reading computed styles) and fall back to documented defaults without a host; a Storybook theme switcher shows the QGIS light and dark palettes; bun run storybook serves and the static build lands in the docs site pipeline.
- [x] #3 release.py stamp/verify-versions/plan know the ui scope and refuse a UI release whose bridge peer range excludes the workspace bridge (tests/scripts); npm pack of qgis-sdk-ui contains dist, README and LICENSE only; the Tier 1 templates opt in through one import and the scaffold-web harness passes.
- [x] #4 decision-16 is promoted with a status review naming the palette tokens as the theme surface; doc-13 documents the components, wrappers and variables; the package README follows decision-29.
- [x] #5 Components are Lit light-DOM elements (no shadow root) with lit as the only dependency in npm pack's tree; the React wrapper uses @lit/react; a page with its own Tailwind/Uno classes renders next to the components without collisions because every shipped utility is qs- prefixed and no preflight is emitted (bun tests + a collision fixture).
- [x] #6 dist/style.css is compiled from the package's own sources by UnoCSS preset-mini, stays within the documented size budget, binds to --qgis-sdk-* tokens so palette switching needs no rebuild, and a consumer without UnoCSS (the vanilla template) renders correctly from it; the optional /uno preset builds the same tokens in a consumer that opts in (scaffold-web harness).
- [x] #7 Every component carries data-qgis-sdk ids and data-part hooks, labels are associated with controls in light DOM, and keyboard focus order follows declaration (Storybook a11y addon + portable-story tests).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: ACs 5-7 added - Lit light DOM, UnoCSS compiled to style.css, data-part/data-qgis-sdk hooks (decision-47 amendment).

Resumed 2026-10-27 after TASK-109 (PR #106). This slice (70d): Storybook 10 (web-components-vite, a11y addon, light/dark switcher in .storybook/preview.ts) with 21 stories over every element against createBridgeHarness; tests/stories.test.ts composes them through storybook/preview-api (render, refusal without grant, label association, focus order ending on the run button); tests/pack.test.ts (npm pack --dry-run: dist/README/LICENSE only, every exports target, lit the one dependency); define.ts exports DEFINED so dist/define.d.ts ships; the scaffold-web harness reads the computed --qgis-sdk-bg/--qgis-sdk-fg and data-qgis-sdk-theme back inside WebEngine against palette_theme() (8 passed with QGIS_SDK_SCAFFOLD_WEB=1); CI builds the Storybook (pixi storybook-build), uploads UI coverage under the qgis-sdk-ui flag and runs the UI tests on macOS/Windows; decision-16 accepted with a status review naming the tokens as the theme surface; doc-13 gains the Components section; README per decision-29. Local gates: UI typecheck, 93 bun tests, coverage, biome, actionlint, ruff, tests/scripts 226. Static Storybook in the docs site waits for TASK-43; the release.yml ui publish job and the scaffold UI pin stamp are TASK-110.

Merged 2026-10-27 as PR #107 (3a2bbcb); main CI green (checks incl. Storybook build and UI coverage upload, cross-platform macOS/Windows with the UI tests). Done. Follow-ups: TASK-110 (release.yml ui publish job, scaffold UI pin stamp), TASK-43 (static Storybook in the docs site).
<!-- SECTION:NOTES:END -->
