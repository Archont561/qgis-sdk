---
id: TASK-98
title: Run the 1.0 API freeze review and the deprecation sweep
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-97
type: task
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-56 point 5. Review every stable symbol against the inventory: remove or mark every pre-1.0 leftover (require_<name>(), NativeForms aliases, old error names), settle naming inconsistencies in one documented minor, confirm doc-22 complete or out of scope by decision, and write the 1.0 migration notes. Output is a reviewed inventory, not new features.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No stable symbol is undocumented, every deprecated symbol has a removal version at or after 1.0, and verify-api between the last 0.x tag and the review commit lists only classified changes.
- [ ] #2 doc-22 shows every row complete or out of scope by decision with a link; doc-12 carries the 1.0 migration notes and the stability policy in the owner's words.
- [ ] #3 A reviewed inventory is committed as the baseline verify-api diffs against after 1.0.
<!-- AC:END -->
