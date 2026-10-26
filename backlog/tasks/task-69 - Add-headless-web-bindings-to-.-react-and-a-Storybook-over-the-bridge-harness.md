---
id: TASK-69
title: Add headless web bindings to ./react and a Storybook over the bridge harness
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
labels: []
milestone: m-6
dependencies:
  - TASK-66
type: enhancement
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-46 points 3 and 5. ./react gains DeclaredForm (renders an action's input schema from the QgisSdk schema and submits), LayerPicker, CrsPicker and FieldPicker (fed by qgis.host, disabled with a reason when the grant is absent), JobProgress (stream handle to progress/state/cancel) and FileRefInput, each as a hook plus a render-prop component; the root exports the same logic as framework-free functions for the vanilla template. packages/qgis-sdk-typescript gains Storybook (@storybook/react-vite): every component has stories mounted in BridgeProvider over createBridgeHarness with scripted replies, faults and grant sets; the stories are the Vitest fixtures through portable stories; the static build is published with the docs site. Stories stay out of the npm tarball; scaffolded plugins do not get Storybook.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each binding is typed from the generated Operations/Streams and the host manifest, works against createBridgeHarness, and the pickers render the refusal when the grant is absent (bun tests through portable stories).
- [ ] #2 bun run storybook serves the stories and the static build lands in the docs site pipeline (TASK-43); npm pack of the bridge contains no story or Storybook file; typecheck, Biome and coverage are green.
- [ ] #3 The React and vanilla scaffold templates use DeclaredForm and LayerPicker in place of the bare button; the scaffold-web harness passes; doc-13 documents the bindings.
<!-- AC:END -->
