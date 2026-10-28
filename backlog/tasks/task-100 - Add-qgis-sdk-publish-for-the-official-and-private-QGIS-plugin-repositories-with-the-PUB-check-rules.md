---
id: TASK-100
title: >-
  Add qgis-sdk publish for the official and private QGIS plugin repositories
  with the PUB check rules
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
updated_date: '2026-10-28 16:24'
labels: []
milestone: m-11
dependencies:
  - TASK-64
  - TASK-77
type: enhancement
ordinal: 100000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-58 points 1, 2 and 5. qgis-sdk publish --repository qgis|<dir>|<url> uploading the built ZIP (plugins.qgis.org XML-RPC, or a generated plugins.xml for private repositories) with credentials from the environment or user keyring only, --dry-run; PUB00x rules in check and build (required metadata keys and lengths, experimental vs version, version monotonicity against the last published when reachable, changelog derived from the project's Conventional Commits, license, icon size, no undeclared compiled files, ZIP root layout); the plugin changelog rendered by build.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 publish --dry-run against a recorded repository fixture validates and reports; a real upload is exercised against a local private repository directory producing a plugins.xml QGIS can consume (devtools harness); no credential is ever written to disk by the tools (pure tests).
- [ ] #2 Every PUB rule has a pure test with a failing and a passing project; build refuses on a finding and renders the changelog from commits.
- [ ] #3 doc-12 documents publishing, the private repository layout and the official repository's rules it mirrors.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ecosystem research: evaluate exact built ZIP validation, checksum reporting, explicit prerelease/experimental handling, private repository indexes and optional translation-service integration. Do not silently rebuild the artifact during publish.
<!-- SECTION:NOTES:END -->
