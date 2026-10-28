---
id: TASK-119
title: Enforce honest Processing output safety for explicit destinations
status: Done
assignee: []
created_date: '2026-10-28 15:58'
updated_date: '2026-10-28 19:18'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
NativeAlgorithms.run passes explicit destinations to Processing and cleans only the SDK-owned run directory on failure. A sandbox probe using a simulated failing Processing backend confirmed an externally written partial file remains. There is no input/output alias check; arbitrary registered providers may have other side effects. Existing no-partial-output and never-edit-input documentation overclaims these guarantees. No input corruption was demonstrated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Design and implement safe handling for explicit and allocated destinations, including input aliases and existing user files; never delete or replace user data blindly. Fail closed where the promised guarantee cannot be provided.
- [x] #2 Test failed runs and successful runs with external, existing, aliased and SDK-allocated destinations, plus native provider cases; distinguish fake-backend evidence from real QGIS provider guarantees.
- [x] #3 Document precise cleanup, atomicity and trusted third-party algorithm limitations and reconcile Algorithms protocol and guide promises; preserve declared contract compatibility or document a breaking migration.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Qualify existing Processing destination and provider behavior; add public Algorithms.run regression coverage for explicit/allocated destinations and fake/native parity; enforce a fail-closed boundary that never deletes or replaces user data blindly; document trusted-provider, cleanup, atomicity and migration limits; run native and workspace checks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented and merged in PR #127. Omitted destinations use a newly created SDK-owned run directory with qualified provider names/extensions. At most one explicit destination is accepted: a new local GeoJSON or GeoPackage vector file. Existing files, aliases, unsupported formats/URIs and multiple named destinations are refused. Native runs stage beside the destination, validate the actual OGR format, independence and absence of sidecars, recheck write grants, then publish without overwrite using a hard link. Cleanup is best-effort, and trusted providers can write or modify data elsewhere; a complete published file can remain if result conversion fails. Documentation and migration notes describe the compatibility restriction and limits. Fake/native tests cover rejected input aliases, external/existing paths, allocated outputs, successful native GeoJSON/GeoPackage, failure cleanup, output races, revoked grants, invalid provider results and sidecars; simulated provider failures are distinguished from real native/GDAL runs. Native-enabled services plus fake/model tests: 238 passed. Workspace coverage: six tasks successful, Python 1928 passed, 62 skipped, 96.97%. Whole-tree Ruff, 262 release-tool tests, backlog doctor and docs link check passed. Windows/macOS native execution not tested locally.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented fail-closed Processing destination planning and staged no-overwrite publication, documented trusted-provider and cleanup limitations, and added fake and native tests. Merged in PR #127 (114c5fd67a4a52b42500aba743244809016bdb85). Local native suite: 238 passed; workspace Python coverage: 1928 passed, 62 skipped, 96.97%. PR checks and post-merge CI, docs and autorelease workflows passed.
<!-- SECTION:FINAL_SUMMARY:END -->
