---
id: TASK-23
title: Qualify candidate QGIS 4 Windows and Linux toolchains
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 21:10'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    backlog/decisions/decision-17 -
    Deliver-a-qualified-Python-first-vertical-slice-for-v1.md
priority: high
type: spike
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Qualify candidate QGIS 4 Windows and Linux toolchains. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Record actual candidate QGIS/Python/Qt/Chromium builds rather than treating the Pixi pin as qualification.
- [ ] #2 Demonstrate repeatable headless/Desktop/WebEngine setup where available and document platform prerequisites.
- [x] #3 Publish evidence and blockers for missing targets without claiming universal QGIS 4 support.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16 qualification evidence (Linux only; unverified restore environment):
- Host: Debian GNU/Linux 12 (bookworm), kernel 6.1.158+, x86_64.
- Candidate QGIS: 4.2.3-Belém do Pará (code branch release 4.2), installed via Pixi default env.
- Python: 3.14.8 (.pixi/envs/default/bin/python).
- Qt: 6.11.2 (QtCore QT_VERSION_STR); PyQt6 Python bindings present, PyQt6.QtWebEngineWidgets/QtWebEngineCore import unavailable in this environment.
- Qt WebEngine C++/resources present at 6.11.2; Chromium version not exposed through available Python bindings; QGIS WebEngine/Desktop Python smoke not yet qualified.
- Headless/repeatable setup: QT_QPA_PLATFORM=offscreen .pixi/envs/default/bin/qgis_process list succeeds and enumerates processing algorithms; qgis --version reports 4.2.3.
- Blockers: no Windows QGIS candidate was available or tested; no Xvfb/display for Desktop GUI smoke; WebEngine Python bindings absent; restore integrity still unverified (pixi-sandbox issue #170), so this is an environment qualification note, not a claim of universal QGIS 4 support.
- Evidence commands: qgis --version; qgis_process list with QT_QPA_PLATFORM=offscreen; Python import qgis.core.Qgis and PyQt6.QtCore.
<!-- SECTION:NOTES:END -->
