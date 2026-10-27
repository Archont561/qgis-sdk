---
id: TASK-110
title: Publish @archont561/qgis-sdk-ui from release.yml and stamp the scaffold UI pin
status: In Progress
assignee: []
created_date: '2026-10-27 13:49'
updated_date: '2026-10-27 14:57'
labels:
  - release
  - ui
milestone: m-6
dependencies: []
priority: medium
type: enhancement
ordinal: 110000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-70 ships the components package with release.py knowing the ui scope (classify, stamp, verify-versions, plan refuse a peer-range mismatch) but release.yml has no job that packs and publishes @archont561/qgis-sdk-ui, and stamp --scope ui leaves the scaffold's UI_NPM_VERSION where it was. Close that gap so a ui-vX.Y.Z tag reaches npm the way typescript-v tags do (trusted publishing, decision-33), and so a UI release moves the pin qgis-sdk new --ui-dependency writes, mirroring stamp_scaffold_pin for the bridge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 release.yml has a ui job gated on the classify output that builds the bridge and the UI package, runs npm pack --dry-run, checks the tarball holds dist, README and LICENSE only, and publishes @archont561/qgis-sdk-ui with trusted publishing; -rc.N tags publish under the next tag
- [ ] #2 release.py stamp --scope ui moves UI_NPM_VERSION in scaffold/web.py and verify-versions reports a stale scaffold UI pin, covered by tests/scripts/test_release.py
- [ ] #3 doc-14 (workspace guide, release section) names the ui scope, its ui-v tag prefix and the scaffold pin a UI release moves
- [ ] #4 The unscoped alias qgis-sdk-ui (packages/qgis-sdk-ui-alias) mirrors @archont561/qgis-sdk-ui entry for entry at the exact pinned version (decision-33 shape), stamp --scope ui moves it, its tests run in CI and the ui job packs, smoke-tests and publishes it after the scoped package
<!-- AC:END -->
