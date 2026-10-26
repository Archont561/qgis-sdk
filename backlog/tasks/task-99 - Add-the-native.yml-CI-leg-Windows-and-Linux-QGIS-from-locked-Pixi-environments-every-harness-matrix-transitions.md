---
id: TASK-99
title: >-
  Add the native.yml CI leg: Windows and Linux QGIS from locked Pixi
  environments, every harness, matrix transitions
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-33
type: chore
ordinal: 99000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-57. A native.yml workflow running the native suite and every QGIS_SDK_* harness offscreen on ubuntu-latest and windows-latest from locked Pixi environments with conda-forge qgis for the LTR and latest 4.x series, nightly and on release branches; SUPPORT_MATRIX rows gain candidate status and the workflow run as evidence; release.py plan refuses a shrinking qualified set without a decision link; doc-12 table regenerated; TASK-33 AC 1 rows resolved or their blocker named.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 native.yml is green on both OSes for the LTR series with every harness reported individually; the Windows QGIS 4 row moves to qualified with the run as evidence; a failing harness on one OS fails the leg visibly (observed runs recorded).
- [ ] #2 A new series enters as candidate from conda-forge and becomes qualified only by its leg; release.py plan refuses a plan whose qualified rows shrank (tests/scripts).
- [ ] #3 doc-12's matrix and qgis-sdk targets agree with the workflow; QGIS 3 / Qt5 is stated out of scope by decision; macOS stays unqualified with the reason.
<!-- AC:END -->
