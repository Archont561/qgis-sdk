---
id: TASK-114
title: >-
  Remove or wire the two bridge errors the TypeScript client exports but never
  throws
status: To Do
assignee: []
created_date: '2026-10-27 21:55'
labels: []
milestone: m-11
dependencies: []
priority: low
type: chore
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-10-27 (clean-code core-yagni-features). packages/qgis-sdk-typescript/src/bridge/errors.ts:59 QgisSdkBridgeSequenceError and :82 QgisSdkBridgeStreamEndedError are exported from the published ./bridge entry (src/bridge.ts:27-28, pinned by tests/index.test.ts:45-46) but no source path constructs either: grep 'new QgisSdkBridgeSequenceError|new QgisSdkBridgeStreamEndedError' over src/ is empty. The client reports a missed frame as a {kind: 'gap'} terminal (src/bridge/client.ts:329), which is the documented contract. The only construction is tests/bridge.test.ts:393-412, added in d3aa848 purely so the per-file 90% coverage gate passed after the bridge split - a constructor test standing in for behaviour nobody has. Resolve one way: remove (delete both classes, the two barrel lines, the surface pin and the coverage test; record under Removed in the package CHANGELOG for the next 0.x minor) or wire (a real code path throws each, covered by a behaviour test). This is the kind of pre-1.0 leftover TASK-98's sweep enumerates; doing it earlier keeps it out of the 1.0 inventory. Non-goals: the gap/terminal semantics and the Python side are untouched.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Either neither class exists in src/ and tests/surface and index pins list the remaining five bridge errors, or every exported bridge error is thrown by at least one documented code path and covered by a test that triggers that path rather than calling the constructor.
- [ ] #2 bun run coverage for packages/qgis-sdk-typescript still passes the per-file thresholds without a constructor-only test for errors.ts.
- [ ] #3 The package CHANGELOG names the change (Removed or Added) in the owner's words.
<!-- AC:END -->
