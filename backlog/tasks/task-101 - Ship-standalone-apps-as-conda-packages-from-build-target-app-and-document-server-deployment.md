---
id: TASK-101
title: >-
  Ship standalone apps as conda packages from build --target app and document
  server deployment
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-81
  - TASK-80
type: enhancement
ordinal: 101000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-58 points 3 and 4. build --target app generates a rattler-build recipe (QGIS from conda-forge, the app as a noarch Python package with a console-script launcher) next to the wheel; a guide section with a Docker example for the server plugin (qgis/qgis-server image + QGIS_PLUGINPATH) and the dev --host server loop; native installers stated out of scope by decision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The generated recipe builds with rattler-build where available and the resulting package launches the app headless and with gui=True (build-install harness; recorded or blocked by the sandbox's missing rattler-build).
- [ ] #2 The server Docker example starts, loads the plugin and answers a WMS GetCapabilities with the plugin's filter applied (recorded run or named blocker).
- [ ] #3 doc-12 documents both paths and what is out of scope.
<!-- AC:END -->
