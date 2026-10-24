---
id: TASK-25.5
title: Qualify the native services on a real QGIS host and record the evidence
status: Done
assignee: []
created_date: '2026-10-24 14:28'
updated_date: '2026-10-24 15:17'
labels: []
milestone: m-1
dependencies:
  - TASK-25.2
  - TASK-25.3
  - TASK-25.4
references:
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
  - backlog/tasks/task-33 - Qualify-Windows-macOS-and-Desktop-QGIS-targets.md
parent_task_id: TASK-25
priority: high
type: chore
ordinal: 25500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 5 (TASK-25). The opt-in harness and the evidence record that turn slices 1-4 from "tested in the pure layer" into "qualified on a real host".

The harness belongs in packages/qgis-sdk/scripts (a wheel must not ship a tool that needs QGIS) and its QGIS-free test in packages/qgis-sdk/tests/scripts, following the existing QGIS_SDK_* opt-in pattern. The record must state what a headless host cannot prove: no GUI, canvas, 3D or Windows/macOS claim from here - TASK-33 owns those.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An opt-in harness under packages/qgis-sdk/scripts drives the native services on real QGIS 4.2.3 and is covered by a QGIS-free test in packages/qgis-sdk/tests/scripts that asserts its unavailable-host report instead of skipping silently.
- [x] #2 The recorded evidence names exact QGIS, Python and Qt versions and lists what the headless run cannot prove, with no GUI, Windows or macOS claim.
- [x] #3 TASK-25 notes quote the actual run; no acceptance criterion is checked on intent, and any unproven criterion stays open with its blocker named.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 completed. The harness assembled across TASK-25.1-25.4 became the qualification instrument; this task added the two pieces it was missing and the evidence record.

Added: a `--prefix` entry point (`parse_prefix`, both `--prefix X` and `--prefix=X`) so the harness can be pointed at a candidate root on any host, and so its failure path is drivable; and a QGIS-free test that runs the script against a prefix containing no QGIS and asserts a serialisable JSON report with every stage false, a non-empty `error`, and exit code 1 - the "answers instead of skipping silently" requirement, tested against the real script rather than against the helper.

AC #1: harness at `packages/qgis-sdk/scripts/native_services_smoke.py`, QGIS-free coverage in `packages/qgis-sdk/tests/scripts/test_qualification_native_services.py` (7 tests: report shape, per-stage pass rule, unavailable report, prefix parsing, unusable-host subprocess, fixture presence, plus the opt-in end-to-end run).

AC #2: recorded in [doc-11](../docs/plans/doc-11%20-%20TASK-25-native-services-qualification-evidence.md) with the verbatim JSON report and the exact versions - QGIS 4.2.3-Belém do Pará, Qt 6.11.2, CPython 3.14.8, Linux-6.1.158+ x86_64, offscreen. Six explicit non-claims are listed: nothing visual (no window/canvas/3D/WebEngine), no real Desktop iface, no Windows/macOS, message-log sink content unobservable (only the injected sink proves delivery), no real Processing outputs (TASK-14), and no style rendering fidelity. TASK-33 remains the owner of AC #1/#2 there.

AC #3: the actual run is quoted in doc-11 and in the TASK-25 closeout note rather than paraphrased; the one criterion this slice could not satisfy on intent - observing the default message-log sink - is recorded as a limitation with its reason instead of being checked.

Run quoted (exit 0, `passed: true`): layer `points`, EPSG:4326, fields (id, value), selection [1, 3], one project layer, scope_closed, reads_refused_after_close, settings_round_trip, settings_refused_after_close, notification_delivered, notification_refused_after_close, style_applied, style_incompatible_refused, theme_unchanged - all true, error null.

Validation: package suite 468 passed / 10 skipped pure, 480 passed / 6 skipped with `QGIS_SDK_NATIVE_SERVICES=1 QGIS_SDK_NATIVE_SERVICES_SMOKE=1`; coverage 100.00%; ruff check and format clean; `backlog doctor` clean. Corrected after the fact: the parity suite is 74 tests with the native backend enabled (not 71), and the pure run skips 10 (not 9) - the numbers above are the measured counts.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Native services qualified on real QGIS 4.2.3 with a verbatim report and six explicit non-claims recorded in doc-11; the harness now also proves its own unusable-host path.
<!-- SECTION:FINAL_SUMMARY:END -->
