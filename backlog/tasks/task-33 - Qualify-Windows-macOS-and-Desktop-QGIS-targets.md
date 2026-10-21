---
id: TASK-33
title: 'Qualify Windows, macOS and Desktop QGIS targets'
status: To Do
assignee: []
created_date: '2026-10-17 16:06'
updated_date: '2026-10-21 21:56'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    backlog/tasks/task-23 -
    Qualify-candidate-QGIS-4-Windows-and-Linux-toolchains.md
  - >-
    backlog/decisions/decision-17 -
    Deliver-a-qualified-Python-first-vertical-slice-for-v1.md
  - >-
    backlog/decisions/decision-3 -
    Development-and-distribution-artifacts-are-separate.md
  - doc-7
  - doc-8
priority: high
type: spike
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Qualify the QGIS targets that the Linux sandbox cannot reach: a clean supported Windows QGIS installation, a macOS QGIS candidate, a real QGIS Desktop GUI run and coexistence with another plugin that already uses the optional native runtime. TASK-23 recorded the Linux headless and WebEngine evidence and closed with these targets explicitly unqualified, so they are tracked here instead of being left as loose blockers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Record a clean supported Windows QGIS installation with its Python, Qt and Chromium builds and a successful native import.
- [ ] #2 Demonstrate the QGIS Desktop GUI path on a platform with a display, including the WebEngine host inside a running Desktop session.
- [ ] #3 Demonstrate coexistence with another plugin that already uses the same optional native runtime dependency.
- [ ] #4 Publish evidence and blockers for any target that remains unavailable, without claiming universal QGIS 4 support.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Created at the TASK-23 closeout (2026-10-17) so the targets the Linux sandbox cannot reach stay tracked instead of being left as loose blockers. TASK-23 qualified the Linux headless and Qt WebEngine path and closed with a Windows candidate, a macOS candidate, a real Desktop GUI run and clean-prefix plugin coexistence explicitly unqualified. The headless harness it produced is at packages/qgis-sdk/tests/qualification/webengine_smoke.py and is reusable on the other targets.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 20:17
---
Path correction for the next attempt: the reusable headless harnesses are now at `packages/qgis-sdk/scripts/webengine_smoke.py`, `desktop_lifecycle_smoke.py` and `qt_scheduler_smoke.py` (previously `packages/qgis-sdk/tests/qualification/`). Run them from the repository root of a Windows or macOS candidate with `pixi run -e default python packages/qgis-sdk/scripts/<name>.py`; their QGIS-free tests sit in `packages/qgis-sdk/tests/scripts/` and stay opt-in through `QGIS_SDK_HEADLESS_SMOKE`, `QGIS_SDK_HEADLESS_LIFECYCLE` and `QGIS_SDK_QT_SCHEDULER`. No Desktop, Windows or macOS qualification is claimed.
---

created: 2026-10-21 21:15
---
The scheduler harness was restructured for this port (doc-7): `packages/qgis-sdk/scripts/qt_scheduler_smoke.py` now drives one function per phase over a shared heartbeat sampler, so retuning a Windows or macOS run means changing one phase instead of reading a 208-line function. The sampler's offset rule is unit-tested, and the named constants (`GUI_STALL_SAMPLES`, `CANCELLATION_POLL_ROUNDS`, `POOL_DRAIN_MS`, `LATE_REPORT_DELAY_MS`, `DISPOSED_DRAIN_S`) are the knobs to adjust per platform. Linux evidence is unchanged: same 25 keys, same phase sample counts, same verdict.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): with Actions dark until November there is no runner for Windows or macOS, and the sandbox has neither a display nor non-Linux hardware, so AC1-AC3 stay open. AC4 is the one AC this window can honestly complete: record each unavailable target as a blocker (no CI, no Windows/macOS host, Linux-only headless QGIS 4.2.3) instead of leaving the task with no evidence at all.
---
<!-- COMMENTS:END -->
