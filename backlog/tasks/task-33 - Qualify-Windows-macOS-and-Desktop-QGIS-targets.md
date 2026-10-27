---
id: TASK-33
title: Qualify Windows, macOS and Desktop QGIS targets
status: To Do
assignee: []
created_date: 2026-10-17 16:06
updated_date: '2026-10-27T18:59:00Z'
labels: []
milestone: m-11
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
- [x] #3 Demonstrate coexistence with another plugin that already uses the same optional native runtime dependency.
- [x] #4 Publish evidence and blockers for any target that remains unavailable, without claiming universal QGIS 4 support.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Created at the TASK-23 closeout (2026-10-17) so the targets the Linux sandbox cannot reach stay tracked instead of being left as loose blockers. TASK-23 qualified the Linux headless and Qt WebEngine path and closed with a Windows candidate, a macOS candidate, a real Desktop GUI run and clean-prefix plugin coexistence explicitly unqualified. The headless harness it produced is at packages/qgis-sdk-python/tests/qualification/webengine_smoke.py and is reusable on the other targets.

2026-10-24 (TASK-33 AC #3 & AC #4 completed; GitHub Actions restored):
- AC #3 (optional native-runtime plugin coexistence): Implemented `packages/qgis-sdk-python/scripts/plugin_coexistence_smoke.py` and `packages/qgis-sdk-python/tests/scripts/test_qualification_coexistence.py` (`QGIS_SDK_PLUGIN_COEXISTENCE=1`, 23 tests). In a clean throwaway QGIS 4.2.3-Belem do Para Desktop profile on Linux x86-64 (CPython 3.14.8, Qt 6.11.2, `QT_QPA_PLATFORM=offscreen`), `neighbor_pydantic_probe` loads first and imports `pydantic==2.14.1` and `pydantic_core==2.50.1` into `sys.modules`; `sdk_pydantic_probe` (built on `create_class_factory` and `PydanticContractAdapter` with `SafeJsonInteger`) loads alongside it; both plugins are active simultaneously, share the identical `pydantic` and `pydantic_core._pydantic_core` modules in `sys.modules`, validate and reject payloads independently, and unloading `sdk_pydantic_probe` closes its `ResourceScope` while leaving `neighbor_pydantic_probe` loaded and functional (`passed: true`, `action_result: 7`).
- AC #4 (published evidence and blockers): Updated `packages/qgis-sdk-python/README.md` and `backlog/docs/plans/doc-8` with the full qualification and blocker table. GitHub Actions CI is live again (PR #38 / commit `a023948`): `cross-platform (macos-latest)` (`120842898256`, arm64, CPython 3.14, Bun 1.4.2: 391 collected, 0 failed, 5 skipped; bridge 90 pass) and `cross-platform (windows-latest)` (`120842898251`, x86_64, CPython 3.14, Bun 1.4.2: 391 collected, 0 failed, 6 skipped; bridge 90 pass) qualify the `pip`-installed QGIS-free SDK, `PydanticContractAdapter` (`pydantic-core` native wheel), and TypeScript bridge on macOS and Windows.
- Remaining blockers (AC #1 & AC #2 stay unchecked): AC #1 remains blocked because `pixi.toml` pins `platforms = ["linux-64"]` and neither the sandbox nor the `pip`-only `cross-platform` CI job provisions a Windows or macOS QGIS 4 installation. AC #2 remains blocked because neither the Linux sandbox nor headless CI runners have a display server or `Xvfb` (`QT_QPA_PLATFORM=offscreen` renders no widgets, canvas, 3D or visible in-Desktop `QWebEngineView`). Universal QGIS 4 support is not claimed.

2026-10-24 (blockers restated, status deliberately unchanged):
- AC #1 (a clean supported Windows QGIS installation) cannot be produced from here. `pixi.toml` pins `platforms = ["linux-64"]`, so no Windows environment exists to install QGIS 4 into, and the `cross-platform` CI job installs the QGIS-free SDK with pip rather than QGIS itself. Qualifying it needs a Windows host with a supported QGIS 4 installation; the reusable harness is already in place (`packages/qgis-sdk-python/scripts/webengine_smoke.py`, `desktop_lifecycle_smoke.py`, `qt_scheduler_smoke.py`).
- AC #2 (Desktop GUI path on a platform with a display) cannot be produced either: neither this sandbox nor the CI runners have a display server or `Xvfb`, and `QT_QPA_PLATFORM=offscreen` renders no widgets, no canvas, no 3D view and no visible in-Desktop `QWebEngineView`. It needs a Desktop session on Windows, macOS or a Linux host with a real or virtual display.
- Neither criterion is a to-do this repository can finish, and neither is claimed as passing anywhere. They are carried into the 0.2.0 gate (TASK-28) as *unavailable*, not as evidence.
- The status stays In Progress per doc-10, which forbids inventing a "blocked" status: a task keeps its status and its blocker is named. Closing it as Done would claim two criteria that have not been demonstrated.

TASK-22 (0.5.0, 2026-10-25) adds a Windows blocker row for the reference workflow: doc-14 'Reference plugin through the toolchain' records the Linux x86-64 row (QGIS 4.2.3, Python 3.14.8, Qt 6.11.2, Chromium 140.0.7339.225) and leaves the Windows row blocked - no host, no QGIS-provisioning CI runner. When a Windows QGIS 4 host exists, run QGIS_SDK_REFERENCE=1 pytest packages/qgis-sdk-python/tests/test_reference_example_native.py (needs Bun) and fill that row.

2026-10-26: decision-57 gives AC 1 its mechanism - the native.yml Windows QGIS leg (TASK-99) qualifies the Windows row; this task's rows are closed by that evidence or keep their blocker.

Re-scoped 2026-10-27 from m-0 to m-11 (1.0.0) and set back to To Do: ACs 1 and 2 need a Windows or macOS QGIS Desktop host, which neither CI nor the sandbox provides; TASK-99 (the native.yml CI leg from locked Pixi environments) is what first supplies one, so the remaining qualification rides on it rather than staying In Progress across releases.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 20:17
---
Path correction for the next attempt: the reusable headless harnesses are now at `packages/qgis-sdk-python/scripts/webengine_smoke.py`, `desktop_lifecycle_smoke.py` and `qt_scheduler_smoke.py` (previously `packages/qgis-sdk-python/tests/qualification/`). Run them from the repository root of a Windows or macOS candidate with `pixi run -e default python packages/qgis-sdk-python/scripts/<name>.py`; their QGIS-free tests sit in `packages/qgis-sdk-python/tests/scripts/` and stay opt-in through `QGIS_SDK_HEADLESS_SMOKE`, `QGIS_SDK_HEADLESS_LIFECYCLE` and `QGIS_SDK_QT_SCHEDULER`. No Desktop, Windows or macOS qualification is claimed.
---

created: 2026-10-21 21:15
---
The scheduler harness was restructured for this port (doc-7): `packages/qgis-sdk-python/scripts/qt_scheduler_smoke.py` now drives one function per phase over a shared heartbeat sampler, so retuning a Windows or macOS run means changing one phase instead of reading a 208-line function. The sampler's offset rule is unit-tested, and the named constants (`GUI_STALL_SAMPLES`, `CANCELLATION_POLL_ROUNDS`, `POOL_DRAIN_MS`, `LATE_REPORT_DELAY_MS`, `DISPOSED_DRAIN_S`) are the knobs to adjust per platform. Linux evidence is unchanged: same 25 keys, same phase sample counts, same verdict.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): with Actions dark until November there is no runner for Windows or macOS, and the sandbox has neither a display nor non-Linux hardware, so AC1-AC3 stay open. AC4 is the one AC this window can honestly complete: record each unavailable target as a blocker (no CI, no Windows/macOS host, Linux-only headless QGIS 4.2.3) instead of leaving the task with no evidence at all.
---

author: qgis-sdk agent
created: 2026-10-21 22:45
---
From TASK-1 (PR #26): headless Desktop plugin-manager evidence is locally reproducible (see the `PYTHONHOME`/`DISPLAY`/`offscreen` contract recorded on TASK-24 and `scripts/scaffold_desktop_smoke.py`). That does not unblock this task's display-dependent criterion: the offscreen platform shows no widget and renders nothing, so canvas/3D/WebEngine qualification still needs real macOS, Windows and Linux display candidates, which are not available here and cannot be evidenced while Actions is unavailable.
---

author: qgis-sdk agent
created: 2026-10-24 15:17
---
From TASK-25 closeout (doc-11): the curated native services are now qualified headless on QGIS 4.2.3-Belém do Pará / Qt 6.11.2 / CPython 3.14.8 for layer open, selection reads, explicit project addition, scoped settings, notifications and packaged QML application, with the application theme proven unchanged. This does not touch this task's criteria: AC #1 (clean Windows QGIS installation) and AC #2 (Desktop GUI path, including an in-Desktop QWebEngine host) stay open because the run is offscreen and Linux-only. Reusable on any candidate: scripts/native_services_smoke.py, now with --prefix so a candidate root can be named, reported as JSON.
---

author: qgis-sdk agent
created: 2026-10-24 18:13
---
Blocker restated 2026-10-24, still open by design: AC #1 needs a Windows host with a supported QGIS 4 installation (pixi pins linux-64, and the cross-platform CI job installs the QGIS-free SDK rather than QGIS), and AC #2 needs a display server, which neither the sandbox nor the runners have. Both are carried into the 0.2.0 gate (TASK-28) as unavailable, not as passing evidence. The task keeps In Progress because doc-10 forbids a separate blocked status.
---
<!-- COMMENTS:END -->
