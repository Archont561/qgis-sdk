---
id: TASK-142
title: Detect orphaned generated bridge clients in the CI freshness gate
status: To Do
assignee: []
created_date: '2026-10-29 07:28'
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
- [ ] #1 A regression test runs the actual generated-client freshness seam in an isolated tree and proves that an old tracked generated artifact omitted from the current generator output is reported, with no destructive change to unrelated files.
- [ ] #2 The gate also fails for changed, removed, or renamed generated outputs and passes for the current complete generated set; preserve the existing byte-freshness and useful remediation diagnostics.
- [ ] #3 Keep generator ownership scoped to the bridge artifacts, retain the existing reference-plugin and QGIS Processing checks, and document the exact freshness semantics in the script and CI.
<!-- AC:END -->
