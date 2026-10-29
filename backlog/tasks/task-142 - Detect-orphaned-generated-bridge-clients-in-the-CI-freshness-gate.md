---
id: TASK-142
title: Detect orphaned generated bridge clients in the CI freshness gate
status: In Progress
assignee: []
created_date: '2026-10-29 07:28'
updated_date: '2026-10-29 08:28'
labels: []
milestone: m-2
dependencies: []
references:
  - .github/workflows/ci.yml
  - packages/qgis-sdk-python/scripts/generate_bridge_clients.py
priority: medium
type: bug
ordinal: 142000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The CI comment promises to catch clients that a generator renamed or stopped writing, but regeneration only writes artifacts() and does not remove old files. In an isolated Git fixture, omitting the existing sites.ts entry from artifacts() left the stale tracked file untouched, main returned 0 and git status was clean. A new output can be detected by git status, but a stopped output cannot. Follow up on TASK-17 without requiring alint or changing the public generator contract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A regression test runs the actual generated-client freshness seam in an isolated tree and proves that an old tracked generated artifact omitted from the current generator output is reported, with no destructive change to unrelated files.
- [x] #2 The gate also fails for changed, removed, or renamed generated outputs and passes for the current complete generated set; preserve the existing byte-freshness and useful remediation diagnostics.
- [x] #3 Keep generator ownership scoped to the bridge artifacts, retain the existing reference-plugin and QGIS Processing checks, and document the exact freshness semantics in the script and CI.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Exercise the actual CI generated-client gate in isolated Git trees; detect orphaned owned bridge artifacts non-destructively, preserve freshness and reference checks, and document and verify the exact scope.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Isolated Git fixtures invoke the real CI helper and generator for clean, stopped, changed, removed and renamed outputs, including all three owned artifacts and non-destructive handling of unrelated files. Both generator modes report orphaned .ts files with the exact sample/host source headers under the two owned output directories; files outside that scope or without those headers are not classified. The existing TypeScript Git-status sweep, reference schema and real-QGIS Processing snapshot checks remain in place. Local validation: 285 script tests passed; workspace coverage 6/6 tasks (Python 1,984 passed, 63 skipped, 96.90%); generator --check and CI gate passed; docs link check 7,042 links, 0 broken; Ruff, actionlint and repository policy passed. Processing snapshot passed with a pre-existing missing PDAL HDF plugin dependency warning. Leave task In Progress until merge.
<!-- SECTION:NOTES:END -->
