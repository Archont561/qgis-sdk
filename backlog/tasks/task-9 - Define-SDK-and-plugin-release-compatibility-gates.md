---
id: TASK-9
title: Define SDK and plugin release compatibility gates
status: Done
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-25 20:14'
labels: []
milestone: m-4
dependencies:
  - TASK-8
  - TASK-22
  - TASK-23
references:
  - doc-8
priority: medium
type: chore
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Automate experimental 0.x SDK/bridge/plugin release gates, explicit target qualification, migration notes and package/protocol version independence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Release checks validate package metadata and build outputs on supported environments.
- [x] #2 Supported QGIS, Python, Qt, and operating-system combinations are explicit.
- [x] #3 The Pixi lockfile is relocked and checked against declared dependencies before CI/release relies on it.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done on PR #82 (branch arena/1e3f35a2-qgis-sdk, CI run 40229626725 green: checks, cross-platform windows/macos). Planner fix first: a prerelease tag no longer advances the stable base (plan --scope python --bump minor after python-v0.5.0-rc.1 -> python-v0.5.0 from python-v0.4.0; a suffixed plan continues the candidate train). AC 1: release.yml names the gate at the steps that run it - verify-versions (scoped manifests, tools-to-runtime range, bridge-to-contract pair), the recorded support matrix, twine check in build and in every publish job, the Conda build. AC 2: qgis_sdk_tools.targets.SUPPORT_MATRIX is the one machine-readable source (decision-37); qgis-sdk targets prints it (--json, --qgis-prefix), doc-12 renders it between markers with a test keeping them equal, tests/test_targets_native.py requires the host the native suite runs on to be a qualified row, release.yml writes it to the job summary. Qualified: Linux x86-64 / QGIS 4.2 / Qt 6.11 / Chromium 140 / CPython 3.14; QGIS-free kit on CPython 3.11 (Linux) and 3.14 (windows-latest, macos-latest). Unqualified: Windows and macOS with QGIS (TASK-33). AC 3: named, not added - every CI/autorelease/release job installs with setup-pixi locked: true (a stale pixi.lock fails before anything runs); relock.yml is the only place that moves the lock and runs pixi lock --check ahead of any install.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC1 ('Release checks validate package metadata and build outputs on supported environments') needs the CI matrix, and AC3 is about CI/release relying on a checked lockfile - `pixi lock --check` passes locally (and pixi.lock is untouched by recent work), but there is no guard to record evidence in. AC2 is the one AC this window can advance, and only by writing down what is actually demonstrated (Linux with QGIS 4.1/4.2 and CPython 3.11-3.14) while listing Windows/macOS as candidates pending TASK-33 - that is a support promise, so it is your decision rather than evidence work.
---
<!-- COMMENTS:END -->
