---
id: TASK-23
title: Qualify candidate QGIS 4 Windows and Linux toolchains
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-17 15:14'
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

2026-10-17 observation recorded by the TASK-12 closeout session (environment evidence, unlanded, no task status or criterion changed): PR #8 pinned pyqt6-webengine 6.11.0, so Qt WebEngine bindings now import in the Pixi default environment (PyQt6.QtWebEngineWidgets/QtWebEngineCore OK).

A repeatable headless smoke ran in this sandbox: QT_QPA_PLATFORM=offscreen, PYTHONPATH=<default-prefix>/share/qgis/python, QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True) before creating the application, and QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process'. Result: QGIS 4.2.3 QgsApplication.initQgis() OK, QWebEngineView.setHtml() reported loadFinished True, exitQgis() OK; Chromium logs ANGLE/EGL and dbus errors that do not block the load. Without those flags WebEngine fails with 'eglInitialize: Failed to get system egl display'. This is a headless harness path, not Desktop GUI or plugin-lifecycle qualification.

Side effect to handle when this task resumes: tests/test_webengine_availability.py::test_create_webengine_view_raises_when_unavailable now skips ('Qt WebEngine bindings are installed in this environment'), which leaves adapters/webengine.py lines 39, 50 and 59 uncovered; measured Python production coverage is therefore 98.55% instead of the 100% earlier sessions recorded (the gate remains 90%). No Xvfb and no Windows candidate are available here, so real Desktop GUI and Windows qualification remain open.
<!-- SECTION:NOTES:END -->
