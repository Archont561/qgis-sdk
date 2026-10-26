---
id: doc-27
title: M11 sprint train and 1.0.0 dependency order
type: guide
created_date: '2026-10-26 11:20'
---
# M11 sprint train and 1.0.0 dependency order

**Status:** Planning. Two tasks start early; the rest after the TASK-95
gate. Orders work the m-11 tasks already declare; adds no scope. Sprint
membership lives here and in the milestone body ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

## 1. Where m-11 starts from

0.11.0 leaves a complete feature set with no stability promise, one
qualified native row, no publishing path, English only, unversioned
settings, authority described across eight decisions, and errors that
surface as refusals or tracebacks. Decisions 56–63 each own one of these.

## 2. Dependency read

| Task | Declared dependencies | Startable |
| --- | --- | --- |
| [TASK-99](../../tasks/task-99%20-%20Add-the-native.yml-CI-leg-Windows-and-Linux-QGIS-from-locked-Pixi-environments-every-harness-matrix-transitions.md) `native.yml` leg | TASK-33 | **now** (evidence for every later milestone) |
| [TASK-105](../../tasks/task-105%20-%20Write-doc-26-Authority-and-threat-model-SECURITY.md-and-qgis-sdk-check-security-with-SEC001.md) doc-26 + `check --security` | TASK-84, TASK-76 | after 0.10.0 sprint 1 |
| [TASK-97](../../tasks/task-97%20-%20Declare-API-stability-tiers-generate-the-public-API-inventory-add-release.py-verify-api-and-the-deprecated-API001-mechanism.md) tiers + inventory + verify-api | TASK-95 | after 0.11.0 |
| [TASK-106](../../tasks/task-106%20-%20Add-ctx.log-crash-capture-into-it-the-Report-a-problem-surface-and-qgis-sdk-diagnose-with-no-telemetry.md) `ctx.log`, crash capture, diagnose | TASK-96, TASK-74 | after 0.8.0 |
| [TASK-104](../../tasks/task-104%20-%20Version-plugin-settings-with-migrations-add-first-run-upgrade-and-reset-hooks-and-document-runtime-isolation.md) settings versioning + hooks | TASK-67 | after 0.6.0 |
| [TASK-103](../../tasks/task-103%20-%20Add-i18n-through-Qt-catalogues-shared-with-the-page-and-the-accessibility-rule-UI005.md) i18n + UI005 | TASK-96, TASK-70 | after 0.7.0 |
| [TASK-100](../../tasks/task-100%20-%20Add-qgis-sdk-publish-for-the-official-and-private-QGIS-plugin-repositories-with-the-PUB-check-rules.md) publish + PUB rules | TASK-64, TASK-77 | after 0.7.0 |
| [TASK-101](../../tasks/task-101%20-%20Ship-standalone-apps-as-conda-packages-from-build-target-app-and-document-server-deployment.md) app conda recipe + server guide | TASK-81, TASK-80 | after 0.9.0 |
| [TASK-98](../../tasks/task-98%20-%20Run-the-1.0-API-freeze-review-and-the-deprecation-sweep.md) freeze review + sweep | TASK-97 | last |
| [TASK-107](../../tasks/task-107%20-%20Prepare-and-qualify-1.0.0-release.md) 1.0.0 gate | 95, 97–101, 103–106 | release gate |

## 3. Sprint train

- **Early, alongside m-9/m-10: TASK-99.** The Windows QGIS leg; every
  later native claim gets a second OS. **TASK-105** drafts doc-26 as soon
  as the grant vocabulary exists, so TASK-86..94 cite rows as they land.
- **Sprint 1: TASK-97.** Tiers, `api dump`, `verify-api`, `@deprecated`,
  API001. Everything after it is measured against the inventory.
- **Sprint 2: TASK-106 with TASK-104.** Log service and crash capture;
  settings versioning and hooks - both touch the runtime's start path.
- **Sprint 3: TASK-103.** i18n and accessibility across native and web.
- **Sprint 4: TASK-100 with TASK-101.** Publishing and app packaging.
- **Sprint 5: TASK-98.** The freeze review and deprecation sweep, last so
  it sees every name.
- **Gate: TASK-107.** `python-v1.0.0`; bridge and UI numbers as the owner
  decides; only on an explicit "Release 1.0.0".

## 4. Hygiene at sprint start

- The README's promise is rewritten from the inventory, not before.
- Decisions 23, 27, 48, 49, 51, 52, 54, 55 get status reviews pointing at
  doc-26 (TASK-105 AC 3).
