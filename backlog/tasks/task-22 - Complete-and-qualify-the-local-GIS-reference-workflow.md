---
id: TASK-22
title: Complete and qualify the local GIS reference workflow
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-25 18:51'
labels: []
milestone: m-4
dependencies:
  - TASK-8
  - TASK-21
  - TASK-14
  - TASK-3
  - TASK-19
  - TASK-16
  - TASK-5
  - TASK-26
references:
  - >-
    backlog/decisions/decision-17 -
    Deliver-a-qualified-Python-first-vertical-slice-for-v1.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
  - doc-8
priority: medium
type: feature
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Complete and qualify the local GIS reference workflow. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Local fixture input, selection, Processing and styled outputs have equivalent native/web behavior and preserve source data.
- [ ] #2 Exercise new/check/test/dev/build, explicit exports and cleanup with deterministic pure and real native tests.
- [ ] #3 Record clean-profile Windows/Linux QGIS/Python/Qt/Chromium evidence and inaccessible/failing targets as blockers.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sprint 2 of m-4 (doc-17). Landed on the session branch: qgis_sdk.exports export policy + Layers.export_vector (fake and native, one contract, 9 cases per backend); reference/polygon-output style; qgis_sdk.reference.LocalGisWorkflow (open -> selection -> buffer -> style -> present -> export); examples/reference_plugin written by qgis-sdk new with five declared actions, a vanilla page over the generated client, 12 pure tests on the fakes and 3 qgis-target tests (real Processing, OGR export, NativeForms dispatch); workspace harness tests/test_reference_example_native.py (QGIS_SDK_REFERENCE=1) running new/check/bridge generate --check/test/test --target qgis/Bun test+typecheck+build/build/dev --exercise and driving the built page in a real QWebEngineView next to the native dialog; dev --exercise gained a smoke report for projects without a ping action; Layers.export_vector recorded in DEFERRED_HOST_METHODS (a page never supplies a path). Evidence: doc-14 'Reference plugin through the toolchain' - Linux row recorded, Windows row blocked (TASK-33). Bridge in the real view is the published @archont561/qgis-sdk 0.3.0; no defect, no bridge release.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC3's clean-profile evidence has a Windows half that needs either the cross-platform job or real hardware. The Linux half is reproducible in-sandbox against headless QGIS 4.2.3 - record it as Linux-only rather than rounding it up to 'profiles'.
---
<!-- COMMENTS:END -->
