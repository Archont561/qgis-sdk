---
id: decision-57
title: Support QGIS 4 LTR and latest on Linux and Windows with a native CI leg per row, and keep QGIS 3 out of scope
date: '2026-10-26'
status: accepted
---
## Context

decision-37 states support as a matrix of demonstrated rows; today one
Linux row (QGIS 4.2, Qt 6.11, CPython 3.14) carries every native proof, the
Windows and macOS QGIS rows are `unqualified` (TASK-33), and no policy says
which QGIS 4 series the SDK follows as QGIS moves. doc-1 defers QGIS 3 and
macOS. The catalogue (decision-55), the hosts (decision-52) and the services
(decision-54) all multiply native surface, so an unqualified Windows row
becomes a larger lie every milestone.

## Decision

1. **Window.** The SDK supports the current QGIS 4 LTR series and the
   current latest 4.x series, on Linux x86-64 and Windows x86-64, with the
   CPython and Qt each ships. A new QGIS series enters the matrix as
   `candidate` when conda-forge publishes it and becomes `qualified` when
   its CI leg is green; the oldest series leaves when QGIS drops it. macOS
   stays best-effort (`unqualified` unless a contributor runs the harness)
   until a macOS QGIS leg exists.
2. **QGIS 3 / Qt5 are out of scope by decision.** The runtime imports
   `qgis.PyQt` only (UI004 guards the plugin package), so a Qt5 build may
   work, but no row claims it and no issue about it is a defect.
3. **One native CI leg per qualified row.** A `native.yml` workflow runs
   the native suite and every opt-in harness (`QGIS_SDK_*`, doc-14) on
   `ubuntu-latest` and `windows-latest` from the locked Pixi environments
   (conda-forge `qgis`), nightly and on release branches; `ci.yml` keeps
   the fast path. A row is `qualified` only by this leg's evidence; the
   matrix data (`SUPPORT_MATRIX`) names the workflow run.
4. **Release gates read the matrix.** `release.py plan` refuses a minor
   whose qualified rows shrank since the last tag without a decision link
   in the release notes; the 1.0 gate requires the Windows row qualified.
5. **Qt6-only idioms are allowed**; the catalogue absorbs Qt version
   differences within Qt 6 (enum scoping, deprecated calls) in one place.

## Consequences

- TASK-33's Windows row gets its mechanism (the leg) instead of a blocker
  note; the display-requiring rows run offscreen on both OSes.
- CI minutes grow; the leg is nightly plus release branches, not per push.
- Tasks: TASK-99 (the `native.yml` leg, Windows Pixi environment, matrix
  wiring, candidate/qualified transitions) in m-11, startable earlier.
