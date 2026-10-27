---
id: TASK-110
title: Publish @archont561/qgis-sdk-ui from release.yml and stamp the scaffold UI pin
status: Done
assignee: []
created_date: '2026-10-27 13:49'
updated_date: '2026-10-27 15:33'
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
- [x] #1 release.yml has a ui job gated on the classify output that builds the bridge and the UI package, runs npm pack --dry-run, checks the tarball holds dist, README and LICENSE only, and publishes @archont561/qgis-sdk-ui with trusted publishing; -rc.N tags publish under the next tag
- [x] #2 release.py stamp --scope ui moves UI_NPM_VERSION in scaffold/web.py and verify-versions reports a stale scaffold UI pin, covered by tests/scripts/test_release.py
- [x] #3 doc-14 (workspace guide, release section) names the ui scope, its ui-v tag prefix and the scaffold pin a UI release moves
- [x] #4 The unscoped alias qgis-sdk-ui (packages/qgis-sdk-ui-alias) mirrors @archont561/qgis-sdk-ui entry for entry at the exact pinned version (decision-33 shape), stamp --scope ui moves it, its tests run in CI and the ui job packs, smoke-tests and publishes it after the scoped package
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Merged in PR #109 (803232c), CI/autorelease/publish-sandbox green on main. release.yml ui job (classify-gated, tarball whitelist check, alias smoke install, dry-run under next for -rc.N, trusted publishing scoped-then-alias); stamp --scope ui moves the alias, its pin and UI_NPM_VERSION; verify-versions names a lagging follower; qgis-sdk-ui alias package with 13 Bun tests; doc-14 release scopes table. Rehearsal tag ui-v0.1.0-rc.1 on 803232c -> release.yml run 40531699064 (see doc-14 for the outcome).
<!-- SECTION:NOTES:END -->
