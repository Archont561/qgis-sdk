---
id: TASK-86
title: >-
  Add the features and expressions services: paged iteration, filters, geometry
  models, attribute read, editing sessions, evaluate and validate
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-28 15:59'
labels: []
milestone: m-9
dependencies:
  - TASK-84
  - TASK-102
type: enhancement
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. features.iterate(layer_id, filter=, fields=, page=) with a bounded page size and server-side QgsFeatureRequest filters, get(id), geometry as WKB/WKT/GeoJSON models, attributes as plain values; editing as an explicit session (begin, add/update/delete, commit, rollback) that is view-owned; expressions.evaluate(layer_id, text, feature_id?) and validate(text); fake, native, host operations, grants; the wire-model answers for features, geometry, binary payloads and paging recorded in decision-54's status review.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Iteration pages deterministically over fake and native layers with server-side filters and bounded size; geometry round-trips in all three encodings. Editing commits or rolls back for supported provider configurations, refuses or clearly reports unsupported guarantees, and is disposed with its view; native and stateful tests define the evidence.
- [ ] #2 The host operations stream pages to the page under a grant with the bounded size enforced, evaluate/validate work from the console and the agent, and the regenerated manifest is typed in generated/host.ts.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document the service, paging limits and tested provider-specific atomicity boundaries.
- [ ] #4 Decide whether a Python context-manager convenience complements explicit sessions; specify already-editing and nested sessions, commit and rollback failure, cancellation, scope closure, undo and concurrent changes, without promising multi-provider atomicity unsupported by the host.
- [ ] #5 Assess Pythonic feature, geometry part and vertex iteration including empty, multipart, wrong-type and invalid-index behavior; specify supported forms and bounded wire paging, compare native QGIS 4, and test fake/native behavior.
<!-- AC:END -->
