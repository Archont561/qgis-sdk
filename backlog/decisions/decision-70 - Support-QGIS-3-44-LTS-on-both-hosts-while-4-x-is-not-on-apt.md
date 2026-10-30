---
id: decision-70
title: Support QGIS 3.44 LTS on both hosts while QGIS 4 x is not on apt, with Qt imported through qgis PyQt
date: '2026-10-30'
status: accepted
---

## Context

decision-57 put QGIS 3 and Qt5 out of scope and stated that "the runtime
imports `qgis.PyQt` only, so a Qt5 build may work" - which was true of the
surface, calendar and webview adapters but not of the four that named `PyQt6`
directly (`adapters/qgis/network.py`, `processing.py`, `workers.py`, and the
`QAction` imports), nor of the seven enum spellings that Qt 6 groups and Qt 5
keeps flat. The locked Pixi environment is QGIS 4.2 with Qt 6, so nothing
caught that.

Meanwhile the only QGIS a Linux machine can install from a package repository
is the 3.44 LTS: qgis.org's `noble` suite, which is also the build with
`qgis.server` in it (TASK-80). That build is Qt 5 / PyQt5. A user who installs
the SDK beside the QGIS their distribution actually offers therefore gets a
crash on the first adapter import, and the server row added for TASK-80 proved
the bindings on a QGIS the Desktop half of the SDK could not run on at all.

QGIS 4.x is not on apt yet, and chasing it there is not worth a CI row that
fails weekly: a second, non-blocking job would only confirm that the
repository has not moved.

## Decision

1. **QGIS 3.44 LTS is a supported series, on both hosts.** Until 4.x reaches
   the apt repositories, the LTS is what "QGIS" means for a Linux user, so the
   Desktop host and the server host both run on it, and the matrix carries one
   row that says so (`SUPPORT_MATRIX`, linux x86-64, CPython 3.12, QGIS 3.44,
   Qt 5.15). QGIS 4.x stays qualified exactly where it already is, in the
   locked Pixi environment.
2. **Qt is imported through `qgis.PyQt`.** No adapter names `PyQt6` or `PyQt5`
   at import time: `qgis.PyQt` is the binding the running QGIS ships, so one
   wheel serves both. The two APIs that still differ live in one module,
   `qgis_sdk.adapters._qt`: `qt_enum(owner, group, name)` resolves
   `Qt.DockWidgetArea.LeftDockWidgetArea` (Qt 6) and `Qt.LeftDockWidgetArea`
   (Qt 5), and `action_class()` finds `QAction` in `QtWidgets` (Qt 5) or
   `QtGui` (Qt 6). A new Qt call that is version-specific belongs there, not
   inline in an adapter.
3. **One row, two hosts.** The `QGIS 3.44 LTS` CI job installs
   `qgis`/`qgis-server`/`python3-qgis`, and `scripts/ci.py lts` proves the
   server layer and the Desktop host (offscreen) on the same build. It reports
   the QGIS version, the Qt version and the PyQt binding it found before pytest
   starts, and fails when either host's module collected nothing.
4. **No WebEngine claim on that row.** The LTS job does not run the WebEngine
   layer, so its matrix row leaves the Chromium cell empty and says why. An
   empty cell means "not exercised here", never "known broken".
5. **QGIS 4.x server waits for apt.** The server host on 4.x is not chased with
   a build matrix of its own; when a 4.x build with server bindings reaches the
   repositories, the same row picks it up by installing the newer package, and
   the matrix row moves with it.

## Consequences

- The adapters work on either binding; a plugin written for the SDK runs on the
  LTS its users have, and on 4.x where QGIS 4 is installed.
- `qgis-minimum-version` may be `3.44` for a plugin that targets the LTS; the
  metadata `metadata.txt` renders whatever the author declares, and `check`
  does not impose a floor of its own.
- The LTS row is the evidence for TASK-80 AC 2's binding half as well: the
  scripted `FakeServerInterface` proves the dispatcher everywhere, and this row
  proves the same modules inside a QGIS that has `qgis.server`.
- decision-57 point 2 is narrowed: QGIS 3.44 is in scope on both hosts; other
  3.x series stay out, and no Qt 5 row claims WebEngine.
- A Qt call that needs two spellings is a defect in the adapter, not a note in
  the guide: the row turns red.
