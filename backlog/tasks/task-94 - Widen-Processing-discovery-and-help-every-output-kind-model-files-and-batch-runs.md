---
id: TASK-94
title: >-
  Widen Processing: discovery and help, every output kind, model files and batch
  runs
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4. algorithms.list/describe with help text and parameter models, outputs of every kind (vector, raster, file, folder, number, string, boolean, HTML, multiple layers) as plain models or FileRefs, run_model(FileRef, inputs), batch(requests) as a job with per-item progress; fake, native, host operations, grants; function algorithms may declare each output kind.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every output kind round-trips from a fixture algorithm through execute, the host and the agent; a model file runs; a batch of three reports per-item progress and cancels (native tests).
- [ ] #2 Function algorithms declaring non-vector outputs register correctly in Processing and the native form; host operations regenerated and typed.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document Processing breadth.
<!-- AC:END -->
