---
id: TASK-114
title: >-
  Remove or wire the two bridge errors the TypeScript client exports but never
  throws
status: Done
assignee: []
created_date: '2026-10-27 21:55'
updated_date: '2026-10-27 22:15'
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
- [x] #1 Either neither class exists in src/ and tests/surface and index pins list the remaining five bridge errors, or every exported bridge error is thrown by at least one documented code path and covered by a test that triggers that path rather than calling the constructor.
- [x] #2 bun run coverage for packages/qgis-sdk-typescript still passes the per-file thresholds without a constructor-only test for errors.ts.
- [x] #3 The repository keeps no per-package CHANGELOG; release notes come from release.py plan, which lists breaking commits in their own section. The removal commit therefore carries the ! marker and a BREAKING CHANGE footer scoped by its files to the TypeScript package only (0.x -> minor).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Resolved as remove: QgisSdkBridgeSequenceError and QgisSdkBridgeStreamEndedError deleted from src/bridge/errors.ts with their bridge.ts barrel lines, the index.test.ts error-export pin and the d3aa848 constructor test; the unused BridgeStreamTerminal import went with them. The gap terminal in client.ts is untouched. Gates: biome clean, tsc clean, TS tests 310 pass with bridge/errors.ts at 100% and all files 99.62/99.33, UI tests 100 pass, root typecheck ok, Python test_bridge_generate + contract fixtures 110 pass (they read the TS sources).

Merged in PR #120 (merge commit c4c96f5, 2026-10-27) with CI green on c278dec.
<!-- SECTION:NOTES:END -->
