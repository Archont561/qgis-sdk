---
id: TASK-25.3
title: Scoped settings and notification services
status: Done
assignee: []
created_date: '2026-10-24 14:28'
updated_date: '2026-10-24 15:07'
labels: []
milestone: m-1
dependencies:
  - TASK-25.1
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
parent_task_id: TASK-25
priority: low
type: feature
ordinal: 25300
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 3 (TASK-25). Scoped settings access and the native implementation of the existing `Notifications` Protocol.

Settings are read and written through the injected service only: pure code never reaches a global QSettings instance, which keeps the boundary that tests/test_pure_imports.py guards.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings access goes through the injected service; no core or service-contract module touches a global QSettings instance.
- [x] #2 The native notifications adapter implements the existing Notifications Protocol without widening it, so plugin code stays runtime-agnostic.
- [x] #3 Pure fake-based tests and one real-host check cover both services, including behaviour after the owning scope closes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 implemented (TDD). Note on the session: the sandbox re-cloned mid-session and dropped the local commits and `.pixi`; all file content survived, the environment was restored with scripts/restore.sh plus a frozen Bun install, and the two earlier commits were re-created from the intact tree (94eaa5f, 62a182c). `.coveragerc` was the one casualty - it had not been committed yet - so it is now tracked.

Scope landed: `NativeSettings` (QgsSettings under a required caller prefix, every operation behind `ensure_open()`) and `NativeNotifications` (implements the existing one-method `Notifications` Protocol, default sink is `QgsMessageLog`, optional injected sink for a Desktop message bar). Both fakes in `qgis_sdk.testing` now carry the owner scope too, so the disposal contract is exercised on both backends.

AC #1: settings reach `QgsSettings` only through `qgis_sdk.adapters.qgis`. Guarded twice - the existing pure-layer AST rule forbids any `qgis` import outside the adapters, and a new `test_settings_reach_the_profile_only_through_the_qgis_adapter` rejects any `QgsSettings` reference outside `adapters/qgis`. Verified by mutation: adding `from qgis.core import QgsSettings` to `services/settings.py` failed both tests, then reverted.

AC #2: the Protocol is untouched - still one `info(message)` method, no severity/title/bar parameters. The sink is a constructor concern, so TASK-3 can inject the Desktop message bar without touching plugin code. Delivery is observable: the adapter takes an optional `sink`, and the harness proves an injected sink receives the exact message.

AC #3: three new scope tests (settings get, settings set, notifications) run on both backends, and the real-host harness now covers both services. On QGIS 4.2.3-Belém do Pará / Qt 6.11.2 / CPython 3.14.8 the extended `scripts/native_services_smoke.py` reports `passed: true` with settings_round_trip, settings_refused_after_close, notification_delivered and notification_refused_after_close all true, alongside the layer/project stages. The default message-log sink is executed but not read back: QGIS swallows Python stdout through its own message handler, so claiming to observe that path would be a claim this host cannot support - recorded rather than worked around.

Validation: pure suite 448 passed / 7 skipped; with `QGIS_SDK_NATIVE_SERVICES=1` the contract suite is 62 passed (29 contract tests on each backend plus 4 fake-only); coverage 100.00% (1066 statements); ruff check and format clean; `backlog doctor` clean. Red evidence: the three new scope tests first failed with `DID NOT RAISE QgisSdkScopeClosedError` on the unscoped fakes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Scoped settings and native notifications land on both backends: NativeSettings wraps QgsSettings behind a required prefix and scope, NativeNotifications keeps the one-method contract with a swappable QGIS sink, and the real-host harness covers both including post-close refusal.
<!-- SECTION:FINAL_SUMMARY:END -->
