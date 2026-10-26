---
id: TASK-97
title: >-
  Declare API stability tiers, generate the public API inventory, add release.py
  verify-api and the @deprecated / API001 mechanism
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-95
type: enhancement
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-56 points 1-4. __stability__ on modules and @stable/@evolving marks; qgis-sdk api dump writing the public API (names, signatures, model fields, CLI, rule ids, host operations, catalogue) as JSON; release.py verify-api diffing against the last tag and classifying additive / deprecating / breaking with the SemVer consequence; @deprecated(since=, removal=, use=) in Python and JSDoc in TypeScript; check API001 for a deprecated use; doc-12 Stability section rendered from the inventory.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 api dump is deterministic and complete for every stable module, verify-api classifies a fixture rename as breaking and a fixture addition as additive, and the release gate refuses a breaking change without the required version bump (tests/scripts).
- [ ] #2 A @deprecated symbol warns once, is reported by check as API001 with the replacement and removal version, and verify-api refuses its removal before the window closes (pure tests).
- [ ] #3 doc-12 renders the tier table from the inventory and a tests/scripts check fails when they disagree; every stable module carries its mark.
<!-- AC:END -->
