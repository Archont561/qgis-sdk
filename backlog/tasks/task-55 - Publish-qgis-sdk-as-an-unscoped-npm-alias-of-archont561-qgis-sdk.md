---
id: TASK-55
title: Publish qgis-sdk as an unscoped npm alias of @archont561/qgis-sdk
status: In Progress
assignee: []
created_date: '2026-10-25 10:34'
labels:
  - release
  - tooling
milestone: m-3
dependencies: []
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner request 2026-10-25: reserve both npm names and make both deploy targets, with the unscoped name as a thin alias. packages/qgis-sdk-alias holds one export-star per entry (., ./bridge, ./host, ./react, ./testing) and a manifest that pins @archont561/qgis-sdk at exactly its own version. scripts/release.py stamps and verifies the alias with the bridge (new manifests 'alias package.json' and 'alias dependency' in the typescript scope; packages/qgis-sdk-alias/ counts as a TypeScript change). release.yml packs both tarballs, smoke-installs them together and imports every non-React entry from both names, publishes the scoped package first and the alias second under the npm environment, and attaches both tarballs to the GitHub Release; GitHub Packages stays scoped-only. Operator runbook: publish a 0.0.0 placeholder per name with setup-npm-trusted-publish, bind release.yml/npm as trusted publisher on both access pages before ts-v0.3.0, then deprecate @archont561/qgis-sdk-bridge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 packages/qgis-sdk-alias re-exports every entry of @archont561/qgis-sdk and its Bun tests fail on any drift in entries, version, pin, files or peers
- [ ] #2 scripts/release.py stamp --scope typescript moves the alias version and pin with the bridge, verify-versions names a lagging alias or drifting pin, and alias paths classify as typescript
- [ ] #3 release.yml packs, smoke-tests and publishes the alias after the scoped package with provenance, dry-runs both on prereleases, and ships both tarballs in SHA256SUMS; CI and autorelease run the alias tests
- [ ] #4 The owner has published the placeholders and bound trusted publishing for @archont561/qgis-sdk and qgis-sdk, and ts-v0.3.0 publishes both names (operator step, recorded when done)
<!-- AC:END -->
