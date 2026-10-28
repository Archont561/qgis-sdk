---
id: TASK-135
title: Show the end-to-end one-action plugin authoring story
status: To Do
assignee: []
created_date: '2026-10-28 16:24'
labels: []
dependencies: []
references:
  - examples/simple
  - apps/docs/src/content/docs/start/first-plugin.md
priority: medium
type: docs
ordinal: 135000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner positions QGIS SDK as the next-generation SDK for effortless QGIS plugin authoring. Design a concise, accurate example linking one Python action to a QGIS-free test, native UI and generated typed web call; point to the existing reference plugin instead of promising unimplemented capabilities.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reader can follow the same action and its typed inputs from a working Python declaration through a pure test, a native surface and a generated TypeScript client; examples are sourced from or tested against a real project, not disconnected pseudocode.
- [ ] #2 Clearly identify QGIS 4 target, current experimental status, framework scaffold versus adapter support and native QGIS requirements; do not imply safety defects TASK-118/119 are resolved or worker-first jobs are shipped.
- [ ] #3 Choose a durable docs source and link it from the README or getting-started flow without duplicating generated content; validate the documented commands and documentation links.
<!-- AC:END -->
