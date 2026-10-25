---
id: TASK-19
title: Scaffold vanilla and React web projects through validated questionnaires
status: Done
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T12:22:00Z'
labels: []
milestone: m-3
dependencies:
  - TASK-1
  - TASK-18
  - TASK-17
references:
  - >-
    backlog/decisions/decision-18 -
    Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
priority: medium
type: feature
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scaffold vanilla and React web projects through validated questionnaires. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Interactive and no-input flags share one validated generation plan for vanilla/React, dialog/dock and npm/pnpm/Bun.
- [x] #2 Vite apps and Vitest tests work with selected package managers; Bunup remains library tooling.
- [x] #3 Dependency install is opt-in; controlled templates validate names/collisions, preserve files on install failure and include checked-in bindings.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered in PR #70. `qgis-sdk new` gained a terminal questionnaire (web UI none/vanilla/react, dialog/dock, npm/pnpm/bun, install now) and the matching flags `--web --placement --package-manager --install/--no-install --no-input`; both feed `ScaffoldOptions.resolve`, one validated plan. The web plan writes a Vite app under `web/` with every dependency pinned exactly (`@archont561/qgis-sdk@0.3.0`), Vite and Vitest for every manager (Bunup stays library tooling), a checked-in generated `src/bridge.ts` with `run bindings` as the drift check, a QWebChannel transport, a vanilla or React page and a Vitest test over the scripted host, plus `<plugin>/webview.py` (BrowserPolicy + Dispatcher, dialog or dock) and a thin Desktop wrapper in `plugin.py`. Install is opt-in; a failed install keeps every file and prints the retry command; `web` and `tests` are reserved names. `new` now takes the runtime through `ctx.obj` (decision-34 amendment). Evidence: unit tests for plan, templates and CLI; opt-in `QGIS_SDK_SCAFFOLD_WEB=1` harness ran install, Vitest, tsc and Vite build with bun 1.4.2, npm 10.9.8 and pnpm 10.34.8 for both frameworks and clicked Ping in the built page under a headless QgsApplication (QGIS 4.2.3, Chromium 140): 12 passed. Docs: doc-12 Web UI section, doc-14 harness entry, decision-34 amendment.
<!-- SECTION:NOTES:END -->
