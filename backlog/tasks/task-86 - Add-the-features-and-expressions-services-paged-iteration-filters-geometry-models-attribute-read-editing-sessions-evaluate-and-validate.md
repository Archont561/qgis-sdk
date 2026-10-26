---
id: TASK-86
title: >-
  Add the features and expressions services: paged iteration, filters, geometry
  models, attribute read, editing sessions, evaluate and validate
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-84
type: enhancement
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. features.iterate(layer_id, filter=, fields=, page=) with a bounded page size and server-side QgsFeatureRequest filters, get(id), geometry as WKB/WKT/GeoJSON models, attributes as plain values; editing as an explicit session (begin, add/update/delete, commit, rollback) that is view-owned; expressions.evaluate(layer_id, text, feature_id?) and validate(text); fake, native, host operations, grants; the wire-model answers for features, geometry, binary payloads and paging recorded in decision-54's status review.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Iteration pages deterministically over the fake and a native layer with the same contract tests, filters are applied server-side (request inspection), geometry round-trips in all three encodings, and an editing session commits or rolls back atomically and dies with its view (native + stateful tests).
- [ ] #2 The host operations stream pages to the page under a grant with the bounded size enforced, evaluate/validate work from the console and the agent, and the regenerated manifest is typed in generated/host.ts.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document the service and the paging limits.
<!-- AC:END -->
