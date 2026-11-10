---
id: TASK-167
title: Burn down the Clean Code budget, starting with the runtime's largest definitions
status: To Do
assignee: []
created_date: '2026-11-10 11:50'
labels: []
dependencies: []
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-166 makes the Clean Code metrics a gate by freezing today's 939 findings as `clean_code_budget.json`. This task is the other half: the budget only ratchets if somebody turns the ratchet, and the largest entries are the ones worth turning first, because they are the definitions a change to the runtime has to read before it can be changed safely. Each slice extracts cohesive helpers behind unchanged behaviour and lowers the budget in the same commit; the budget diff is the evidence, since nothing else in the repository records that a function got shorter.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The five largest definitions are split behind unchanged public behaviour: `bridge/dispatch.py` (756-line class), `http/_server.py` (699-line class, 379-line function), `bridge/host/_handlers.py` (602-line function), `generate/_generator.py` (588-line class) and `bridge/authority.py` (520-line class).
- [ ] #2 Each slice lowers `clean_code_budget.json` in the same commit, and the existing suites pass without a test rewritten to fit the new shape.
- [ ] #3 The outstanding findings are recorded by rule and by file in this task, so the next slice does not have to re-measure the tree.
- [ ] #4 After the five slices, the thresholds are reviewed: any metric the tree now meets everywhere is tightened in `[tool.rude]` and the budget re-baselined, so the ratchet moves rather than the number merely shrinking.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Baseline from TASK-166: 939 findings in 268 files - CC101 480, CC104 125, CC102 120, CC303 77, CC103 35, CC201 33, CC202 29, CC302 26, CC301 4. CC301 (nesting) is the closest to clean with 4 findings and is worth taking first: it is the rule whose fix is most often "return early", and the smallest diff of the set.
<!-- SECTION:NOTES:END -->
