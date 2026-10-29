---
id: TASK-135
title: Show the end-to-end one-action plugin authoring story
status: In Progress
assignee: []
created_date: '2026-10-28 16:24'
updated_date: '2026-10-29 09:11'
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
- [x] #1 A reader can follow the same action and its typed inputs from a working Python declaration through a pure test, a native surface and a generated TypeScript client; examples are sourced from or tested against a real project, not disconnected pseudocode.
- [x] #2 Clearly identify QGIS 4 target, current experimental status, framework scaffold versus adapter support and native QGIS requirements; do not imply safety defects TASK-118/119 are resolved or worker-first jobs are shipped.
- [x] #3 Choose a durable docs source and link it from the README or getting-started flow without duplicating generated content; validate the documented commands and documentation links.
- [x] #4 Verify the getting-started scaffold command and displayed file tree against the actual default and native UI scaffold outputs; correct the misleading surfaces.py claim and distinguish the optional ui.py generated with --ui native.
- [x] #5 Coordinate the one-action walkthrough and any generated-file or architecture visualizations with TASK-138 so examples remain accurate and shared rather than duplicated.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Use one real example project to demonstrate the same action through QGIS-free tests, native UI and the typed web bridge. Verify scaffold outputs and documentation commands through executable tests, then build and link-check the docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The durable first-plugin guide follows the real examples/simple buffer action through the Python declaration, fake-service test, native Form.for_action and generated typed web client. Regression tests check verbatim source excerpts and execute the documented default, native and vanilla-web scaffold commands, including the actual ui.py and bridge.schema.ts paths. The guide distinguishes QGIS 4/experimental status, adapters versus scaffolds, fakes and native requirements. Local validation: reference pure check/test 20 passed; reference web tests 6 passed; native scaffold check/test/build produced an installable ZIP (4 pure tests passed); real offscreen QGIS Desktop scaffold ZIP smoke passed and qgis-sdk dev reload test passed. Documentation built with 7050 internal links, zero broken. Workspace coverage 6/6, Python 1991 passed, 56 skipped, 7 deselected, 96.90%. Keep In Progress pending merge.

The reference project native QGIS target also passed 7 tests, including its native buffer dialog and direct action path; this is offscreen Linux evidence, not visible GUI or other-platform qualification.
<!-- SECTION:NOTES:END -->
