---
id: TASK-25
title: Implement curated native services and packaged style support
status: Done
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 15:17'
labels: []
milestone: m-1
dependencies:
  - TASK-24
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-16 -
    Separate-reusable-layer-styles-from-UI-themes.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - >-
    backlog/tasks/task-38 -
    Epic-v2-0.2.0-native-runtime-and-Processing-algorithms.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
  - >-
    backlog/docs/plans/doc-11 -
    TASK-25-native-services-qualification-evidence.md
priority: medium
type: feature
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement curated native services and packaged style support. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Provide typed layer/project/notification/settings contracts with matching fake/native tests for real workflows.
- [x] #2 Validate layer lifetime, selection, output ownership and scoped resource operations without mirroring all PyQGIS.
- [x] #3 Apply reviewed packaged QML to compatible outputs and inherit native UI theme without global stylesheet mutation.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 slicing (v2 sprint 1): this task is now decomposed into five sub-tasks that carry the executable criteria, because one 3-AC task covering contracts, a PyQGIS adapter, settings, styles and qualification was too large to plan or review as a unit. TASK-25.1 contracts + in-memory fakes (no dependency); TASK-25.2 native layer/project adapter and TASK-25.3 settings/notifications both depend on 25.1 and can run in parallel; TASK-25.4 packaged QML depends on 25.2; TASK-25.5 real-host qualification depends on 25.2, 25.3 and 25.4. The acceptance criteria above stay at this level and are checked only when the corresponding slices are closed with evidence. Nothing about scope changed: slices 1-5 are the plan already recorded in doc-9 and the pre-existing criteria, not new commitments.

2026-10-24 closeout: all five slices are Done - TASK-25.1 contracts and fakes, 25.2 native layer/project adapter, 25.3 scoped settings and notifications, 25.4 packaged QML, 25.5 qualification. Evidence record: [doc-11](../docs/plans/doc-11%20-%20TASK-25-native-services-qualification-evidence.md).

Actual run quoted rather than summarised (`pixi run -e default python packages/qgis-sdk-python/scripts/native_services_smoke.py`, exit 0, QGIS 4.2.3-Belém do Pará / Qt 6.11.2 / CPython 3.14.8 / Linux-6.1.158+ x86_64 / offscreen): `passed: true`, `error: null`, layer `points` with `layer_geometry_type: point`, fields `(id, value)`, `layer_crs: EPSG:4326`, `selection: [1, 3]`, one `project_layer_ids` entry, and `scope_closed`, `reads_refused_after_close`, `settings_round_trip`, `settings_refused_after_close`, `notification_delivered`, `notification_refused_after_close`, `style_applied`, `style_incompatible_refused`, `theme_unchanged` all true.

AC #1: Layers, Project, Settings and Notifications contracts with fake/native pairings - one contract suite runs 74 tests across both backends, and the fakes share the catalog compatibility rule rather than re-declaring results.
AC #2: layer lifetime, selection reads, explicit output ownership and scoped resource operations are contract-level, with post-close refusal proven on every operation and no PyQGIS mirror (nothing edits geometry or attributes; selection is read-only by design).
AC #3: reviewed packaged QML applies to compatible outputs; an incompatible target is refused before anything is applied; and the application stylesheet plus six palette roles are asserted unchanged, so native theme inheritance is untouched rather than merely undamaged by inspection.

Not proven here and deliberately not claimed: the visually rendered result, a real Desktop iface, Windows and macOS, the default message-log sink's content, and behaviour across a real Processing run (TASK-14). TASK-33 owns the display-dependent and non-Linux targets; its AC #1 and AC #2 remain open.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Curated native services and packaged styling complete across five slices: four contracts with one parity suite on both backends, scoped ownership with proven post-close refusal, packaged QML with theme proven untouched, and a headless qualification record on QGIS 4.2.3 (doc-11).
<!-- SECTION:FINAL_SUMMARY:END -->
