---
id: TASK-167
title: Burn down the Clean Code budget, starting with the runtime's largest definitions
status: In Progress
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
**Slice 1 (landed): the branch rules, not the size rules.** 939 -> 893 findings, no file left with more of anything than it had. CC103 35 -> 19, CC302 26 -> 8, CC303 77 -> 70, CC101 486 -> 481; two files left the budget entirely (`qgis_sdk_tools/rest.py`, `qgis_sdk_tools/ui_yaml.py`).

What the slice changed: guard clauses and lookups instead of return chains (`_item_kind`, `_transport_failure`, `_send`, `_name`, `_scalar`, `_coerce`, `_schema`, `emit`, `pull`, `_step`); named predicates instead of long boolean chains (`_is_number`, `_is_bare_origin`, `_is_local_path`, `_is_module_member`, the `_server` parameter validators); and one table where a chain of `if` was a mapping (`_ACCESSORS`, `_FAILURE_CLASSES`, `_TYPE_NAMES`, `_CONVERTERS`, `_ITEM_KINDS`). Two extras were needed to keep the ratchet honest rather than to shrink anything: `Job._ready` moved to a module function so the step machine's helpers did not push the class past 200 lines, and `Subscription`'s frame handling folded into `_queue_frame` so it stayed at 15 methods.

**What is left.** The size rules are the budget now: CC101 481, CC104 128, CC102 121, CC303 70, CC202 29 / CC201 33, plus 19 CC103 in functions that are themselves too long (`dispatch.dispatch` 19 returns, `processing._value` 16, `_parameter` 15, `form.input_for` 13, `_emit._inline_validator` 15, `webengine._decide` 11, `expressions._compare` 10), 8 CC302 in `tests/smoke_support`, and 4 CC301 (`release._cmd_verify_versions`, `_server._rest_stream`, `_server._close`, `check/jobs._imports_in_body`).

The next slice pays twice if it starts where the returns are: `dispatch.dispatch` is inside the 756-line class, so splitting the endpoint's decisions is the same work as splitting the class. That is why AC 1's five largest definitions are the entry point.

<!-- SECTION:NOTES:BEGIN -->
Baseline from TASK-166: 939 findings in 268 files - CC101 486, CC104 128, CC102 121, CC303 77, CC103 35, CC201 33, CC202 29, CC302 26, CC301 4. CC301 (nesting) is the closest to clean with 4 findings and is worth taking first: it is the rule whose fix is most often "return early", and the smallest diff of the set.
<!-- SECTION:NOTES:END -->
