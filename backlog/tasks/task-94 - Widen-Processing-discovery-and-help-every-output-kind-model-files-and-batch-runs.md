---
id: TASK-94
title: >-
  Processing: model files and batch runs; function algorithms declare every
  output kind
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-27 11:17'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4, narrowed on 2026-10-27 when TASK-109 pulled discovery, describe, the generated registry and the generic run forward into m-6. What stays here: run_model(FileRef, inputs) for .model3 files, batch(requests) as a job with per-item progress and cancellation, and function algorithms declaring each output kind (raster, file, folder, number, string, boolean, HTML, multiple layers) so they register correctly in Processing and the native form; fake, native, host operations and grants for those.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A model file runs through run_model and its outputs come back as the kinds the generated registry describes; a batch of three reports per-item progress and cancels (native tests).
- [ ] #2 Function algorithms declaring non-vector outputs register correctly in Processing and the native form; host operations regenerated and typed.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document model files and batch runs.
<!-- AC:END -->
