---
id: TASK-23
title: Qualify candidate QGIS 4 Windows and Linux toolchains
status: Done
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-17 16:06'
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
- [x] #2 Demonstrate repeatable headless/Desktop/WebEngine setup where available and document platform prerequisites.
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

2026-10-17 repeatable headless and WebEngine setup (AC #2, Linux only; unverified restore environment):

- A checked-in harness now exists at packages/qgis-sdk-python/tests/qualification/webengine_smoke.py. It resolves the QGIS prefix, the PROJ data directory and the QGIS Python path from the active prefix, sets QT_QPA_PLATFORM=offscreen and QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process, starts a real QgsApplication, loads a page in a real QWebEngineView and prints a machine-readable JSON report. Run it with: pixi run -e default python packages/qgis-sdk-python/tests/qualification/webengine_smoke.py
- Verified result in this sandbox: qualified=true, qgis_version=4.2.3-Belem do Para, qt_version=6.11.2, chromium_version=140.0.0.0, python_version=3.14.8, load_finished=true, qgis_exited=true, exit code 0, about one second of runtime. The Chromium version is read from the Qt WebEngine user agent, which closes the earlier note that the Chromium build was not exposed by the available bindings.
- The end-to-end test is tests/test_qualification_webengine.py with QGIS_SDK_HEADLESS_SMOKE=1; it runs the harness as a subprocess and asserts the report. The harness helpers (environment overrides, user-agent parsing, report shape) are covered by the always-on QGIS-free suite, and packages/qgis-sdk-python/README.md documents the platform prerequisites.
- Without the Chromium flags the WebEngine process fails with eglInitialize: Failed to get system egl display. ANGLE, EGL, dbus and PDAL messages during a run are noise and do not affect the result.
- The coverage side effect of PR #8 is resolved: adapters/webengine.py previously left lines 39, 50 and 59 uncovered because tests/test_webengine_availability.py skipped the unavailable-bindings branch when the bindings are installed. That branch is now exercised deterministically by hiding the candidate modules through sys.modules, so the environment-dependent skip is gone and measured Python production coverage is back to 100% against the 90% gate. The only remaining skip is the opt-in headless smoke.
- Still not qualified, recorded as prerequisites: no Windows QGIS candidate, no macOS QGIS candidate, no display and no Xvfb for a real QGIS Desktop GUI run, and no clean-prefix plugin coexistence test. This is a headless harness path, not a Desktop GUI or plugin-lifecycle qualification.
- Validation for this change: root test 192 Python passed/1 skipped and 90 bridge passed; coverage Python 100% and bridge 100% against the 90% gates; Ruff lint/format, Biome, bridge typecheck, actionlint, skill-creator tests (25 passed), pixi lock --check, wheel/sdist build with Twine and git diff --check all pass. The Conda recipe build is still blocked on conda-forge repodata access (tls handshake eof) and was not rerun. No dependency or lockfile change; no production source change.

2026-10-17 landed: PR #10 merged as a37def9; post-merge CI checks, plan and publish succeeded. The headless harness and its documentation are in main, and the unavailable targets are tracked by the new TASK-33. Closed by user decision after the Linux headless and WebEngine evidence was accepted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #10 merged as a37def9aa2057fd808d67e2f5df09448756cf74d; post-merge CI (checks, plan, publish) succeeded. Demonstrated on Linux x86_64 with QGIS 4.2.3-Belem do Para, Qt 6.11.2, Chromium 140.0.0.0 and Python 3.14.8: a repeatable headless setup that starts a real QgsApplication, loads a page in a real QWebEngineView and exits cleanly, delivered as the checked-in harness packages/qgis-sdk-python/tests/qualification/webengine_smoke.py and documented with its platform prerequisites in the package README. All three acceptance criteria are met as written. Explicitly NOT qualified and now tracked by TASK-33: a clean supported Windows QGIS installation, a macOS QGIS candidate, a real QGIS Desktop GUI run (this sandbox has no display and no Xvfb) and coexistence with another plugin that already uses the optional native runtime. This is a headless harness qualification, not a universal QGIS 4 support claim, and it does not qualify the plugin lifecycle or the bridge. The sandbox restore still fails nine RECORD integrity comparisons, so the environment is an unverified restore and no platform qualification beyond this Linux host is claimed.
<!-- SECTION:FINAL_SUMMARY:END -->
