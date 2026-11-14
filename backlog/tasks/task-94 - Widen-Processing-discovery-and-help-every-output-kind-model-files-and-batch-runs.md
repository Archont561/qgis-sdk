---
id: TASK-94
title: >-
  Processing: model files and batch runs; function algorithms declare every
  output kind
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-14 17:05'
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
- [x] #1 A model file runs through run_model and its outputs come back as the kinds the generated registry describes; a batch of three reports per-item progress and cancels (native tests).
- [x] #2 Function algorithms declaring non-vector outputs register correctly in Processing and the native form; host operations regenerated and typed.
- [x] #3 doc-22 rows complete; doc-12/doc-13 document model files and batch runs.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Closed 2026-11-14: it shipped in 0.11.0 and the record had not caught up.** The
task sat in `To Do` through the release that carried it - `ts-v0.8.0`'s notes
list `feat(processing): model files, batch runs and every output kind
(TASK-94)`, and doc-22's "Processing breadth (0.11.0)" row is `complete
(TASK-94)`. Each criterion is checked against the tree rather than the release
notes:

* **AC 1** - `Algorithms.run_model(model, params)` walks a granted `.model3`
  ref and answers the kinds the registry declares (`services/algorithms.py`),
  and `qgis_sdk/batch.py` runs a batch as one job with a fraction per item and
  a cancellation check between them. The native tests are the evidence:
  `test_a_batch_of_three_reports_runs_one_report_each` and
  `test_a_batch_of_three_reports_reports_one_fraction_per_report` in
  `tests/services/test_algorithms_native.py` run three `native:statistics`
  reports against a real QGIS.
* **AC 2** - the catalogue declares nine `OutputKind` rows
  (`models/processing/_catalogue.py`), and the regenerated host manifest
  carries `algorithms.run_model` and `algorithms.batch` in
  `packages/qgis-sdk-typescript/src/generated/host.ts`.
* **AC 3** - doc-22's row is complete and doc-12's "Model files: `run_model`,
  and batches as a job (0.11.0)" section documents both, including the
  cancelled-batch and empty-batch refusals.

Discovery and help were narrowed to TASK-109 during the train (decision-54
point 4), which doc-22's row records, so no part of the task was dropped
silently.

**Documentation impact.** None: this note corrects the record, and the guides,
the manifest and the behaviour are unchanged.
<!-- SECTION:NOTES:END -->
