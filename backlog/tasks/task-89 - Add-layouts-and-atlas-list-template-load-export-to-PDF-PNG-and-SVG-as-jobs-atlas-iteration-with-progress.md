---
id: TASK-89
title: >-
  Add layouts and atlas: list, template load, export to PDF, PNG and SVG as
  jobs, atlas iteration with progress
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-84
type: enhancement
ordinal: 89000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. layouts.list, load_template(FileRef), export(layout_id, format, FileRef, settings) as a @job with progress and cancellation (QgsLayoutExporter), atlas.run(layout_id, FileRef pattern) as a job yielding one FileRef per page; fake, native, host operations, grants; export files are owned temporary outputs or author-granted paths.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Export and atlas run as jobs visible in the task manager, produce the files, report progress and cancel cleanly, with fake and native sharing the contract tests (native tests, offscreen rendering).
- [ ] #2 Host operations regenerated and typed; the page and the agent receive FileRefs, never paths; the destructive annotation covers overwrite.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document layouts; the example exports a PDF.
<!-- AC:END -->
